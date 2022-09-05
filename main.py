import os
import logging
import time
import datetime
import binascii

logging.basicConfig(format='%(asctime)s %(levelname)s [%(name)s] %(message)s', level=logging.INFO)

logger = logging.getLogger(__name__)

from read_minimed_next24 import Medtronic600SeriesDriver, HISTORY_DATA_TYPE, PumpStatusResponseMessage
from pump_history_parser import AlarmNotificationEvent, AlarmClearedEvent, NGPHistoryEvent
from homeassistant_uploader import HomeAssistantUploader


class PumpConnector:
    def __init__(self, uploader):
        self._uploader = uploader

        self._connected_successfully = False
        self._connection_timestamp = datetime.datetime.now()
        self._mt = None

    def get_and_upload_data(self) -> None:
        self._connected_successfully = False

        self._start_communication()

        if not self._connected_successfully:
            self._uploader.update_status("Not connected.")
            self._reset_all_states()
            self._connection_timestamp = datetime.datetime.now()

        self._uploader.update_timestamp(state=self._connection_timestamp.strftime("%H:%M:%S %d.%m.%Y"))
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
                events = self._get_pump_events()

                if not events:
                    self._uploader.update_event("")  # Reset message
                else:
                    for event in events:
                        logger.info(events[event])
                        self._uploader.update_event(str(events[event]))
                        time.sleep(1)  # time to process event on Homeassistant

            self._connected_successfully = True
            self._connection_timestamp = status.sensorBGLTimestamp
        except Exception:
            logger.error("Unexpected error in while downloading data", exc_info=True)
            raise

    def wait(self) -> None:
        minimum_waiting_time_in_seconds = 30
        maximum_waiting_time_in_seconds = 6 * 60

        waiting_time = self._connection_timestamp.replace(tzinfo=None) + \
                       datetime.timedelta(minutes=5, seconds=30) - datetime.datetime.now()

        waiting_time_in_seconds = waiting_time.seconds
        if waiting_time_in_seconds < minimum_waiting_time_in_seconds:
            waiting_time_in_seconds = minimum_waiting_time_in_seconds
        if waiting_time_in_seconds > maximum_waiting_time_in_seconds:
            waiting_time_in_seconds = maximum_waiting_time_in_seconds

        time.sleep(waiting_time_in_seconds)

    def _get_pump_events(self) -> dict:
        start_date = datetime.datetime.now() - datetime.timedelta(minutes=10)
        history_pages = self._mt.getPumpHistory(None, start_date, datetime.datetime.max,
                                                HISTORY_DATA_TYPE.PUMP_DATA)
        events = self._mt.processPumpHistory(history_pages, HISTORY_DATA_TYPE.PUMP_DATA)

        events_found = {}
        for event in events:
            if type(event) == AlarmNotificationEvent:
                events_found[self._get_pump_event_id(event)] = event
            if type(event) == AlarmClearedEvent:
                if self._get_pump_event_id(event) in events_found:
                    del events_found[self._get_pump_event_id(event)]

        return events_found

    @staticmethod
    def _get_pump_event_id(event: NGPHistoryEvent):
        return binascii.hexlify(event.eventData[0x0B:][0:2])

    def _update_states(self, medtronic_pump_status: PumpStatusResponseMessage) -> None:
        if self._data_is_valid(medtronic_pump_status):
            self._uploader.update_status("Connected.")

            self._uploader.update_bgl(state=medtronic_pump_status.sensorBGL)
            self._uploader.update_trend(state=medtronic_pump_status.trendArrow)
            self._uploader.update_active_insulin(state=medtronic_pump_status.activeInsulin)
            self._uploader.update_current_basal_rate(state=medtronic_pump_status.currentBasalRate)
            self._uploader.update_temp_basal_rate(state=medtronic_pump_status.tempBasalRate)
            self._uploader.update_temp_basal_rate_percentage(state=medtronic_pump_status.tempBasalPercentage)
            self._uploader.update_pump_battery_level(state=medtronic_pump_status.batteryLevelPercentage)
            self._uploader.update_insulin_units_remaining(state=medtronic_pump_status.insulinUnitsRemaining)
        else:
            self._uploader.update_status("Invalid data.")
            self._reset_all_states()

    def _reset_all_states(self) -> None:
        self._uploader.update_bgl(state="")
        self._uploader.update_trend(state="")
        self._uploader.update_active_insulin(state="")
        self._uploader.update_current_basal_rate(state="")
        self._uploader.update_temp_basal_rate(state="")
        self._uploader.update_temp_basal_rate_percentage(state="")
        self._uploader.update_pump_battery_level(state="")
        self._uploader.update_insulin_units_remaining(state="")
        self._uploader.update_event(state="")

    @staticmethod
    def _data_is_valid(medtronic_pump_status: PumpStatusResponseMessage) -> bool:
        return str(medtronic_pump_status.sensorBGLTimestamp.strftime(
            "%d.%m.%Y")) != "01.01.1970" and 0 < medtronic_pump_status.sensorBGL < 700


if __name__ == '__main__':
    TOKEN = os.getenv("HOMEASSISTANT_TOKEN")
    IP = os.getenv("HOMEASSISTANT_IP")
    PORT = os.getenv("HOMEASSISTANT_PORT")

    uploader = HomeAssistantUploader(token=TOKEN, ip=IP, port=PORT)
    pump_connector = PumpConnector(uploader=uploader)

    while True:
        try:
            pump_connector.get_and_upload_data()
        except BaseException as ex:
            print(ex)
        pump_connector.wait()
