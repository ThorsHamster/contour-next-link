import logging
import time
import datetime
import binascii
import subprocess

logger = logging.getLogger('app')

from read_minimed_next24 import Medtronic600SeriesDriver, HISTORY_DATA_TYPE, PumpStatusResponseMessage
from pump_history_parser import AlarmNotificationEvent, AlarmClearedEvent, NGPHistoryEvent, InsulinDeliveryStoppedEvent
from homeassistant_connector import HomeAssistantConnector


class PumpConnector:
    def __init__(self, connector: HomeAssistantConnector):
        self._ha_connector = connector

        self._connected_successfully = False
        self._connection_timestamp = self._get_datetime_now()
        self._mt = None
        self._set_change_timestamp = None

    def get_and_upload_data(self) -> None:
        self._connected_successfully = False

        self._start_communication()

        if not self._connected_successfully:
            self._ha_connector.update_status("Not connected.")
            self.reset_all_states()
            self._reset_timestamp_after_fail()

        self._ha_connector.update_timestamp(state=self._connection_timestamp.strftime("%H:%M:%S %d.%m.%Y"))
        self._mt = None

    def _start_communication(self) -> None:
        try:
            self._mt = Medtronic600SeriesDriver()

            if self._mt is None:
                logger.warning("Loading of device driver failed. Try to reset device.")
                self._ha_connector.update_status("Driver fail.")
                self._reset_timestamp_after_fail()
                self._reset_usb_device()
                return

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
                self._reset_timestamp_after_fail()
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
                self._reset_timestamp_after_fail()

            self._connected_successfully = True
        except Exception:
            logger.error("Unexpected error while downloading data", exc_info=True)
            raise

    def wait(self) -> None:
        minimum_waiting_time_in_seconds = 30

        switched_state = self._ha_connector.switched_on()

        if switched_state:
            waiting_time = self._connection_timestamp.replace(tzinfo=None) + \
                           datetime.timedelta(minutes=5, seconds=30)
        else:
            waiting_time = self._get_datetime_now() + datetime.timedelta(minutes=5)

        if (waiting_time - self._get_datetime_now()).seconds < minimum_waiting_time_in_seconds:
            waiting_time = self._get_datetime_now() + datetime.timedelta(seconds=30)

        while waiting_time > self._get_datetime_now():
            time.sleep(5)
            if self._ha_connector.switched_on() is not switched_state:
                break

    def _get_datetime_now(self) -> datetime.datetime:
        return datetime.datetime.now()

    def _request_pump_events(self) -> list:
        start_date = self._get_datetime_now() - datetime.timedelta(minutes=10)
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

    def _is_pump_event_new(self, event: NGPHistoryEvent) -> bool:
        time_delta = self._get_datetime_now() - event.timestamp.replace(tzinfo=None)
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

    def _reset_timestamp_after_fail(self):
        self._connection_timestamp = self._get_datetime_now()

    @staticmethod
    def _reset_usb_device():
        logger.warning("Reset of USB drive. User needs sudo permissions for this file!")
        proc = subprocess.Popen(['sudo', './install/usb_reset.sh'])
        proc.wait()