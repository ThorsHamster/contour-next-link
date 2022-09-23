import os
import logging
import logging.handlers as handlers
import time
import datetime
import binascii

logging.basicConfig(format='%(asctime)s %(levelname)s [%(name)s] %(message)s', level=logging.INFO)

logger = logging.getLogger('app')

logHandler = handlers.RotatingFileHandler('log.txt', maxBytes=1000, backupCount=2)
logger.addHandler(logHandler)

from read_minimed_next24 import Medtronic600SeriesDriver, HISTORY_DATA_TYPE, PumpStatusResponseMessage
from pump_history_parser import AlarmNotificationEvent, AlarmClearedEvent, NGPHistoryEvent, InsulinDeliveryStoppedEvent
from homeassistant_connector import HomeAssistantConnector


class PumpConnector:
    def __init__(self, connector):
        self._ha_connector = connector

        self._connected_successfully = False
        self._connection_timestamp = datetime.datetime.now()
        self._mt = None
        self._set_change_timestamp = None

    def get_and_upload_data(self) -> None:
        self._connected_successfully = False

        self._start_communication()

        if not self._connected_successfully:
            self._ha_connector.update_status("Not connected.")
            self.reset_all_states()
            self._connection_timestamp = datetime.datetime.now()

        self._ha_connector.update_timestamp(state=self._connection_timestamp.strftime("%H:%M:%S %d.%m.%Y"))
        self._mt = None

    def _start_communication(self) -> None:
        try:
            self._mt = Medtronic600SeriesDriver()
            self._mt.openDevice()
            self._enter_control_mode()
        finally:
            self._mt.closeDevice()

    def _enter_control_mode(self) -> None:
        try:
            self._mt.getDeviceInfo()
            logger.info("Device serial: {0}".format(self._mt.deviceSerial))
            self._mt.enterControlMode()
            self._enter_passthrough_mode()
        finally:
            self._mt.exitControlMode()

    def _enter_passthrough_mode(self) -> None:
        try:
            self._mt.enterPassthroughMode()
            self._open_connection()
        finally:
            self._mt.exitPassthroughMode()

    def _open_connection(self) -> None:
        try:
            self._mt.openConnection()
            self._mt.readInfo()
            self._mt.readLinkKey()
            try:
                self._mt.negotiateChannel()
                self._begin_high_speed_mode()
            except Exception:
                logger.error("Cannot connect to the pump. Abandoning")
                self._connection_timestamp = datetime.datetime.now()
                return
        finally:
            self._mt.closeConnection()

    def _begin_high_speed_mode(self) -> None:
        try:
            self._mt.beginEHSM()
            # We need to read always the pump time to store the offset for later messaging
            self._mt.getPumpTime()
            self._get_and_upload_data()
        finally:
            self._mt.finishEHSM()

    def _get_and_upload_data(self) -> None:
        try:
            status = self._mt.getPumpStatus()
            self._update_states(status)

            if self._data_is_valid(status):
                events = self._request_pump_events()

                self._get_set_change_timestamp(events)
                if self._set_change_timestamp is not None:
                    self._ha_connector.update_latest_set_change(self._set_change_timestamp.strftime("%A"))
                else:
                    self._ha_connector.update_latest_set_change("")

                not_acknowledged_alarms = self._get_not_acknowledged_pump_alarms(events)

                if not not_acknowledged_alarms:
                    self._ha_connector.update_event("")  # Reset message
                else:
                    for not_acknowledged_alarm in not_acknowledged_alarms:
                        logger.info(not_acknowledged_alarms[not_acknowledged_alarm])
                        event = not_acknowledged_alarms[not_acknowledged_alarm]
                        self._ha_connector.update_event(f"Alarm! {event.timestamp.strftime('%d.%m.%Y %H:%M:%S')}")
                        time.sleep(1)  # time to process event on Homeassistant

                self._connection_timestamp = status.sensorBGLTimestamp
            else:
                self._connection_timestamp = datetime.datetime.now()

            self._connected_successfully = True
        except Exception:
            logger.error("Unexpected error in while downloading data", exc_info=True)
            raise

    def wait(self) -> None:
        minimum_waiting_time_in_seconds = 30

        switched_state = self._ha_connector.switched_on()

        if switched_state:
            waiting_time = self._connection_timestamp.replace(tzinfo=None) + \
                           datetime.timedelta(minutes=5, seconds=30)
        else:
            waiting_time = datetime.datetime.now() + datetime.timedelta(minutes=5)

        if (waiting_time - datetime.datetime.now()).seconds < minimum_waiting_time_in_seconds:
            waiting_time = datetime.datetime.now() + datetime.timedelta(seconds=30)

        while waiting_time > datetime.datetime.now():
            time.sleep(5)
            if self._ha_connector.switched_on() is not switched_state:
                break

    def _request_pump_events(self) -> list:
        start_date = datetime.datetime.now() - datetime.timedelta(minutes=10)
        history_pages = self._mt.getPumpHistory(None, start_date, datetime.datetime.max,
                                                HISTORY_DATA_TYPE.PUMP_DATA)
        events = self._mt.processPumpHistory(history_pages, HISTORY_DATA_TYPE.PUMP_DATA)
        return events

    def _get_not_acknowledged_pump_alarms(self, events: list) -> dict:
        events_found = {}
        for event in events:
            if self._is_pump_event_new(event):
                if type(event) == AlarmNotificationEvent:
                    events_found[self._get_pump_event_id(event)] = event
                if type(event) == AlarmClearedEvent:
                    if self._get_pump_event_id(event) in events_found:
                        del events_found[self._get_pump_event_id(event)]

        return events_found

    def _get_set_change_timestamp(self, events: list) -> None:
        for event in events:
            if type(event) == InsulinDeliveryStoppedEvent:
                if event.suspendReasonText == "Set change suspend":
                    self._set_change_timestamp = event.timestamp
                    break

    @staticmethod
    def _get_pump_event_id(event: NGPHistoryEvent):
        return binascii.hexlify(event.eventData[0x0B:][0:2])

    @staticmethod
    def _is_pump_event_new(event: NGPHistoryEvent) -> bool:
        time_delta = datetime.datetime.now() - event.timestamp.replace(tzinfo=None)
        return time_delta.seconds < 15 * 60

    def _update_states(self, medtronic_pump_status: PumpStatusResponseMessage) -> None:
        if self._data_is_valid(medtronic_pump_status):
            self._ha_connector.update_status("Connected.")

            self._ha_connector.update_bgl(state=medtronic_pump_status.sensorBGL)
            self._ha_connector.update_trend(state=medtronic_pump_status.trendArrow)
            self._ha_connector.update_active_insulin(state=medtronic_pump_status.activeInsulin)
            self._ha_connector.update_current_basal_rate(state=medtronic_pump_status.currentBasalRate)
            self._ha_connector.update_temp_basal_rate_percentage(state=medtronic_pump_status.tempBasalPercentage)
            self._ha_connector.update_pump_battery_level(state=medtronic_pump_status.batteryLevelPercentage)
            self._ha_connector.update_insulin_units_remaining(state=medtronic_pump_status.insulinUnitsRemaining)
        else:
            self._ha_connector.update_status("Invalid data.")
            self.reset_all_states()

    def reset_all_states(self) -> None:
        self._ha_connector.update_bgl(state="")
        self._ha_connector.update_trend(state="")
        self._ha_connector.update_active_insulin(state="")
        self._ha_connector.update_current_basal_rate(state="")
        self._ha_connector.update_temp_basal_rate_percentage(state="")
        self._ha_connector.update_pump_battery_level(state="")
        self._ha_connector.update_insulin_units_remaining(state="")
        self._ha_connector.update_event(state="")

    @staticmethod
    def _data_is_valid(medtronic_pump_status: PumpStatusResponseMessage) -> bool:
        return str(medtronic_pump_status.sensorBGLTimestamp.strftime(
            "%d.%m.%Y")) != "01.01.1970" and 0 < medtronic_pump_status.sensorBGL < 700


if __name__ == '__main__':
    TOKEN = os.getenv("HOMEASSISTANT_TOKEN")
    IP = os.getenv("HOMEASSISTANT_IP")
    PORT = os.getenv("HOMEASSISTANT_PORT")

    home_assistant_connector = HomeAssistantConnector(token=TOKEN, ip=IP, port=PORT)
    pump_connector = PumpConnector(connector=home_assistant_connector)

    while True:
        try:
            if home_assistant_connector.switched_on():
                home_assistant_connector.update_status("Requesting data.")
                pump_connector.get_and_upload_data()
            else:
                home_assistant_connector.update_status("Deactivated.")
                pump_connector.reset_all_states()
                home_assistant_connector.update_timestamp(state=datetime.datetime.now().strftime("%H:%M:%S %d.%m.%Y"))
        except BaseException as ex:
            print(ex)
        pump_connector.wait()
