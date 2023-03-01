from unittest.mock import Mock
import pytest
import datetime

from pump_connector import PumpConnector
from pump_data import MedtronicDataStatus, MedtronicMeasurementData
from pump_history_parser import InsulinDeliveryStoppedEvent, InsulinDeliveryRestartedEvent, AlarmNotificationEvent, \
    AlarmClearedEvent


@pytest.fixture
def medtronic_data_valid():
    return MedtronicMeasurementData(
        bgl_value=120,
        trend="No arrows",
        active_insulin=1.1,
        current_basal_rate=0.123,
        temporary_basal_percentage=75,
        battery_level=75,
        insulin_units_remaining=92,
        status=MedtronicDataStatus.valid,
        timestamp=datetime.datetime(2022, 1, 1, 12, 00, 00, 0)
    )


class TestPumpConnector:
    waiting_time_in_seconds = 5

    def create_unit_under_test(self):
        return PumpConnector(connector=self.mock_connector)

    def mock_dependencies(self, mocker):
        # pylint: disable=attribute-defined-outside-init
        self.mock_connector = mocker.patch("pump_connector.pump_connector.HomeAssistantConnector")
        self.mock_sleep = mocker.patch("pump_connector.pump_connector.time.sleep")
        self.mock_get_datetime_now = mocker.patch("pump_connector.pump_connector.get_datetime_now")
        self.mock_medtronic_driver = mocker.patch("pump_connector.pump_connector.Medtronic600SeriesDriver")
        self.mock_InsulinDeliveryStoppedEvent = Mock(spec=InsulinDeliveryStoppedEvent)
        self.mock_InsulinDeliveryRestartedEvent = Mock(spec=InsulinDeliveryRestartedEvent)
        self.mock_AlarmNotificationEvent = Mock(spec=AlarmNotificationEvent)
        self.mock_AlarmClearedEvent = Mock(spec=AlarmClearedEvent)
        # pylint: enable=attribute-defined-outside-init

    def test_get_and_upload_data_happy_path_no_events(self, mocker, medtronic_data_valid):
        self.mock_dependencies(mocker)

        self.mock_medtronic_driver.return_value.getPumpMeasurement.return_value = medtronic_data_valid

        unit_under_test = self.create_unit_under_test()

        unit_under_test.get_and_upload_data()

        self.mock_connector.update_bgl.assert_called_with(state=medtronic_data_valid.bgl_value)
        self.mock_connector.update_trend.assert_called_with(state=medtronic_data_valid.trend)
        self.mock_connector.update_active_insulin.assert_called_with(state=medtronic_data_valid.active_insulin)
        self.mock_connector.update_current_basal_rate.assert_called_with(state=medtronic_data_valid.current_basal_rate)
        self.mock_connector.update_temp_basal_rate_percentage.assert_called_with(
            state=medtronic_data_valid.temporary_basal_percentage)
        self.mock_connector.update_pump_battery_level.assert_called_with(state=medtronic_data_valid.battery_level)
        self.mock_connector.update_insulin_units_remaining.assert_called_with(
            state=medtronic_data_valid.insulin_units_remaining)
        self.mock_connector.update_status.assert_called_with("Connected.")
        self.mock_connector.update_timestamp.assert_called_with(state="12:00:00 01.01.2022")
        self.mock_connector.update_event.assert_called_with("")

    def test_get_and_upload_data_event_set_change(self, mocker, medtronic_data_valid):
        self.mock_dependencies(mocker)

        self.mock_medtronic_driver.return_value.getPumpMeasurement.return_value = medtronic_data_valid

        self.mock_InsulinDeliveryStoppedEvent.suspendReasonText = "Set change suspend"
        self.mock_InsulinDeliveryStoppedEvent.timestamp = datetime.datetime(2022, 1, 1, 12, 00, 00, 0)
        self.mock_medtronic_driver.return_value.processPumpHistory.return_value = [
            self.mock_InsulinDeliveryRestartedEvent,
            self.mock_InsulinDeliveryStoppedEvent,
            self.mock_InsulinDeliveryRestartedEvent
        ]

        unit_under_test = self.create_unit_under_test()

        unit_under_test.get_and_upload_data()

        self.mock_connector.update_latest_set_change.assert_called_with("Saturday")

    def test_get_and_upload_data_event_low_glucose_prediction_only(self, mocker, medtronic_data_valid):
        self.mock_dependencies(mocker)

        self.mock_medtronic_driver.return_value.getPumpMeasurement.return_value = medtronic_data_valid
        self.mock_get_datetime_now.return_value = datetime.datetime(2022, 1, 1, 12, 4, 00, 0)

        self.mock_InsulinDeliveryStoppedEvent_prediction = Mock(spec=InsulinDeliveryStoppedEvent)
        self.mock_InsulinDeliveryStoppedEvent_prediction.suspendReasonText = "Predicted low glucose suspend"
        self.mock_InsulinDeliveryStoppedEvent_prediction.timestamp = datetime.datetime(2022, 1, 1, 12, 00, 00, 0)

        self.mock_AlarmNotificationEvent.timestamp = datetime.datetime(2022, 1, 1, 12, 00, 1, 0)
        self.mock_AlarmNotificationEvent.eventData = b'032a04020224000f14006056042900600076'

        self.mock_medtronic_driver.return_value.processPumpHistory.return_value = [
            self.mock_AlarmNotificationEvent,
            self.mock_InsulinDeliveryStoppedEvent_prediction
        ]

        unit_under_test = self.create_unit_under_test()

        unit_under_test.get_and_upload_data()

        self.mock_connector.update_event.assert_called_with("")

    def test_get_and_upload_data_event_low_glucose_prediction_and_alarm(self, mocker, medtronic_data_valid):
        self.mock_dependencies(mocker)

        self.mock_medtronic_driver.return_value.getPumpMeasurement.return_value = medtronic_data_valid
        self.mock_get_datetime_now.return_value = datetime.datetime(2022, 1, 1, 12, 4, 00, 0)

        self.mock_InsulinDeliveryStoppedEvent_prediction = Mock(spec=InsulinDeliveryStoppedEvent)
        self.mock_InsulinDeliveryStoppedEvent_prediction.suspendReasonText = "Predicted low glucose suspend"
        self.mock_InsulinDeliveryStoppedEvent_prediction.timestamp = datetime.datetime(2022, 1, 1, 12, 00, 00, 0)

        self.mock_AlarmNotificationEvent.timestamp = datetime.datetime(2022, 1, 1, 12, 00, 1, 0)
        self.mock_AlarmNotificationEvent.eventData = b'032a04020224000f14006056042900600076'

        self.mock_low_glucose_alarm = Mock(spec=AlarmNotificationEvent)
        self.mock_low_glucose_alarm.timestamp = datetime.datetime(2022, 1, 1, 12, 5, 0, 0)
        self.mock_low_glucose_alarm.eventData = b'032a04020224000f14006056042900600076'

        self.mock_medtronic_driver.return_value.processPumpHistory.return_value = [
            self.mock_AlarmNotificationEvent,
            self.mock_InsulinDeliveryStoppedEvent_prediction,
            self.mock_low_glucose_alarm
        ]

        unit_under_test = self.create_unit_under_test()

        unit_under_test.get_and_upload_data()

        self.mock_connector.update_event.assert_called_with(
            f"BGL: {medtronic_data_valid.bgl_value}, {medtronic_data_valid.trend} (01.01.2022 12:05:00)")

    def _generate_datetimes(self, start_datetime: datetime.datetime, end_datetime: datetime.datetime,
                            stepsize: datetime.timedelta) -> list:
        step = start_datetime

        list_of_datetimes = [start_datetime]
        while step < end_datetime:
            step = step + stepsize
            list_of_datetimes.append(step)

        return list_of_datetimes

    def test_wait_standard_waiting_time(self, mocker):
        self.mock_dependencies(mocker)

        self.mock_connector.switched_on.return_value = True
        self.mock_get_datetime_now.side_effect = [datetime.datetime(2022, 1, 1, 12, 00, 00,
                                                                    0)] + self._generate_datetimes(
            start_datetime=datetime.datetime(2022, 1, 1, 12, 00, 00, 0),
            end_datetime=datetime.datetime(2022, 1, 1, 12, 10, 00, 0),
            stepsize=datetime.timedelta(seconds=5))

        unit_under_test = self.create_unit_under_test()

        unit_under_test.wait()

        assert self.mock_sleep.call_count == (5 * 60 + 30) / self.waiting_time_in_seconds

    def test_wait_switch_is_off(self, mocker):
        self.mock_dependencies(mocker)

        self.mock_connector.switched_on.side_effect = 200 * [False]
        self.mock_get_datetime_now.side_effect = [datetime.datetime(2022, 1, 1, 12, 00, 00,
                                                                    0)] + self._generate_datetimes(
            start_datetime=datetime.datetime(2022, 1, 1, 12, 00, 00, 0),
            end_datetime=datetime.datetime(2022, 1, 1, 12, 10, 00, 0),
            stepsize=datetime.timedelta(seconds=5))

        unit_under_test = self.create_unit_under_test()

        unit_under_test.wait()

        assert self.mock_sleep.call_count == (5 * 60) / self.waiting_time_in_seconds

    def test_wait_switch_is_off_switches_on_while_waiting(self, mocker):
        self.mock_dependencies(mocker)

        self.mock_connector.switched_on.side_effect = 20 * [False] + [True]
        self.mock_get_datetime_now.side_effect = [datetime.datetime(2022, 1, 1, 12, 00, 00,
                                                                    0)] + self._generate_datetimes(
            start_datetime=datetime.datetime(2022, 1, 1, 12, 00, 00, 0),
            end_datetime=datetime.datetime(2022, 1, 1, 12, 10, 00, 0),
            stepsize=datetime.timedelta(seconds=5))

        unit_under_test = self.create_unit_under_test()

        unit_under_test.wait()

        assert self.mock_sleep.call_count == 20

    def test_wait_test_minimum_time(self, mocker):
        self.mock_dependencies(mocker)

        invalid_data = datetime.datetime(1970, 1, 1, 12, 00, 00, 0)

        self.mock_connector.switched_on.return_value = True
        self.mock_get_datetime_now.side_effect = [invalid_data] + self._generate_datetimes(
            start_datetime=datetime.datetime(2022, 1, 1, 12, 00, 00, 0),
            end_datetime=datetime.datetime(2022, 1, 1, 12, 10, 00, 0),
            stepsize=datetime.timedelta(seconds=5))

        unit_under_test = self.create_unit_under_test()

        unit_under_test.wait()

        assert self.mock_sleep.call_count == 30 / self.waiting_time_in_seconds
