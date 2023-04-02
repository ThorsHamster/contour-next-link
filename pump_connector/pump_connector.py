import logging
import time
import datetime
import binascii
import subprocess

logger = logging.getLogger('app')

from read_minimed_next24 import Medtronic600SeriesDriver, HISTORY_DATA_TYPE
from pump_history_parser import AlarmNotificationEvent, AlarmClearedEvent, NGPHistoryEvent, InsulinDeliveryStoppedEvent, \
    InsulinDeliveryRestartedEvent
from homeassistant_connector import HomeAssistantConnector
from pump_connector.helper import get_datetime_now
from pump_data import MedtronicDataStatus, MedtronicMeasurementData


class PumpConnector:
    def __init__(self, connector: HomeAssistantConnector):
        self._ha_connector = connector

        self._connected_successfully = False
        self._connection_timestamp = get_datetime_now()
        self._mt = None
        self._set_change_timestamp = None
        self._time_difference_in_seconds = 0

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

            self._mt.openDevice()

            self._enter_control_mode()
        finally:
            if self._mt.device is None:
                logger.warning("Loading of device driver failed. Try to reset device.")
                self._ha_connector.update_status("Driver fail.")
                self._reset_timestamp_after_fail()
                self._reset_usb_device()
                return

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
            pump_time = self._mt.getPumpTime()
            self._time_difference_in_seconds = self._get_time_diff_in_seconds(pump_time.datetime)
            self._get_and_upload_data()
        finally:
            self._mt.finishEHSM()

    def _get_time_diff_in_seconds(self, pump_datetime: datetime.datetime) -> int:
        try:
            time_diff = get_datetime_now().replace(tzinfo=None) - pump_datetime.replace(tzinfo=None)
            return int(time_diff.total_seconds())
        except Exception:
            return 0

    def _get_and_upload_data(self) -> None:
        try:
            status = self._mt.getPumpMeasurement()
            self._update_states(status)

            if self._data_is_valid(status):
                self._connection_timestamp = status.timestamp
            else:
                self._reset_timestamp_after_fail()
            self._connected_successfully = True

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
                    self._ha_connector.update_event(
                        f"BGL: {status.bgl_value}, {status.trend} ({event.timestamp.strftime('%d.%m.%Y %H:%M:%S')})")
                    time.sleep(1)  # time to process event on Homeassistant

            if self._data_is_valid(status):
                self._connection_timestamp = status.timestamp
            else:
                self._reset_timestamp_after_fail()

            self._connected_successfully = True
        except Exception:
            logger.error("Unexpected error while downloading data", exc_info=True)
            raise

    def wait(self) -> None:
        minimum_waiting_time_in_seconds = 30

        switched_state = self._ha_connector.switched_on()

        datetime_now = get_datetime_now()

        if switched_state:
            waiting_time = self._connection_timestamp.replace(tzinfo=None) + \
                           datetime.timedelta(minutes=5, seconds=30)
            waiting_time = waiting_time + datetime.timedelta(seconds=self._time_difference_in_seconds)
        else:
            waiting_time = datetime_now + datetime.timedelta(minutes=5)

        difference = waiting_time - datetime_now
        if difference.total_seconds() < minimum_waiting_time_in_seconds:
            waiting_time = datetime_now + datetime.timedelta(seconds=30)

        while waiting_time >= get_datetime_now():
            time.sleep(5)
            if self._ha_connector.switched_on() is not switched_state:
                break

    def _request_pump_events(self) -> list:
        start_date = get_datetime_now() - datetime.timedelta(minutes=10)
        history_pages = self._mt.getPumpHistory(None, start_date, datetime.datetime.max,
                                                HISTORY_DATA_TYPE.PUMP_DATA)
        events = self._mt.processPumpHistory(history_pages, HISTORY_DATA_TYPE.PUMP_DATA)
        return events

    def _get_not_acknowledged_pump_alarms(self, events: list) -> dict:
        events_found = {}
        timestamps_to_ignore = []  # necessary, because all InsulinDeliveryStoppedEvent and
        # InsulinDeliveryRestartedEvent, also have a AlarmNotificationEvent, which should be ignored for now
        for event in events:
            if self._is_pump_event_new(event):
                if self._events_to_ignore(event):
                    timestamps_to_ignore.append(event.timestamp)
                else:
                    if isinstance(event, AlarmNotificationEvent):
                        events_found[self._get_pump_event_id(event)] = event
                    if isinstance(event, AlarmClearedEvent):
                        if self._get_pump_event_id(event) in events_found:
                            del events_found[self._get_pump_event_id(event)]

        # remove all events in ignored timeframe. Unfortunately it is not possible to distinguish, which
        # AlarmNotificationEvent corresponds to which InsulinDeliveryStoppedEvent except the time.
        delete = []
        for not_acknowledged_alarm in events_found:
            event = events_found[not_acknowledged_alarm]
            if self._is_in_list_of_ignored_timestamps(event.timestamp, timestamps_to_ignore):
                delete.append(self._get_pump_event_id(event))
        for i in delete:
            del events_found[i]

        return events_found

    def _get_set_change_timestamp(self, events: list) -> None:
        for event in events:
            if isinstance(event, InsulinDeliveryStoppedEvent):
                if event.suspendReasonText == "Set change suspend":
                    self._set_change_timestamp = event.timestamp

    @staticmethod
    def _events_to_ignore(event) -> bool:
        if isinstance(event, InsulinDeliveryStoppedEvent):
            if event.suspendReasonText == "Predicted low glucose suspend":  # ignore suspended because of low glucose
                return True
        if isinstance(event, InsulinDeliveryRestartedEvent):
            if event.resumeReasonText == "Low glucose auto resume - preset glucose reached":  # ignore auto resume
                return True
        return False

    @staticmethod
    def _is_in_list_of_ignored_timestamps(timestamp: datetime.datetime, list_of_timestamps: list) -> bool:
        for comparison_timestamp in list_of_timestamps:
            if comparison_timestamp - datetime.timedelta(
                    seconds=1) <= timestamp <= comparison_timestamp + datetime.timedelta(seconds=1):
                return True
        return False

    @staticmethod
    def _get_pump_event_id(event: NGPHistoryEvent):
        return binascii.hexlify(event.eventData[0x0B:][0:2])

    def _is_pump_event_new(self, event: NGPHistoryEvent) -> bool:
        time_delta = get_datetime_now() - event.timestamp.replace(tzinfo=None)
        return time_delta.total_seconds() < 15 * 60

    def _update_states(self, medtronic_pump_data: MedtronicMeasurementData) -> None:
        if self._data_is_valid(medtronic_pump_data):
            self._ha_connector.update_status("Connected.")

            self._ha_connector.update_bgl(state=medtronic_pump_data.bgl_value)
            self._ha_connector.update_trend(state=medtronic_pump_data.trend)
            self._ha_connector.update_active_insulin(state=medtronic_pump_data.active_insulin)
            self._ha_connector.update_current_basal_rate(state=medtronic_pump_data.current_basal_rate)
            self._ha_connector.update_temp_basal_rate_percentage(state=medtronic_pump_data.temporary_basal_percentage)
            self._ha_connector.update_pump_battery_level(state=medtronic_pump_data.battery_level)
            self._ha_connector.update_insulin_units_remaining(state=medtronic_pump_data.insulin_units_remaining)
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
        
    def clear_messages(self) -> None:
        try:
            if self._mt is None:
                self._mt = Medtronic600SeriesDriver()

                self._mt.openDevice()
            self._mt.clearMessage()
        finally:
            if self._mt.device is None:
                return

            self._mt.closeDevice()

    @staticmethod
    def _data_is_valid(medtronic_pump_data: MedtronicMeasurementData) -> bool:
        return medtronic_pump_data.status is MedtronicDataStatus.valid

    def _reset_timestamp_after_fail(self):
        self._connection_timestamp = get_datetime_now()

    @staticmethod
    def _reset_usb_device():
        logger.warning("Reset of USB drive. User needs sudo permissions for this file!")
        proc = subprocess.Popen(['sudo', './install/usb_reset.sh'])
        proc.wait()
