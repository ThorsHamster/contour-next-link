from unittest.mock import MagicMock
import datetime

from pump_connector import PumpConnector


class TestPumpConnector:

    waiting_time_in_seconds = 5

    def create_unit_under_test(self):
        return PumpConnector(connector=self.mock_connector)

    def mock_dependencies(self, mocker):
        # pylint: disable=attribute-defined-outside-init
        self.mock_connector = mocker.patch("pump_connector.pump_connector.HomeAssistantConnector")
        self.mock_sleep = mocker.patch("pump_connector.pump_connector.time.sleep")
        self.mock_get_datetime_now = mocker.patch("pump_connector.pump_connector.get_datetime_now")
        # pylint: enable=attribute-defined-outside-init

    def _generate_datetimes(self, start_datetime: datetime.datetime, end_datetime: datetime.datetime,
                            stepsize: datetime.timedelta) -> list:
        step = start_datetime

        list_of_datetimes = [start_datetime, start_datetime]  # double first entry, because of init of PumpConnector
        while step < end_datetime:
            step = step + stepsize
            list_of_datetimes.append(step)

        return list_of_datetimes

    def test_wait_standard_waiting_time(self, mocker):
        self.mock_dependencies(mocker)

        self.mock_connector.switched_on.return_value = True
        self.mock_get_datetime_now.side_effect = self._generate_datetimes(
            start_datetime=datetime.datetime(2022, 1, 1, 12, 00, 00, 0),
            end_datetime=datetime.datetime(2022, 1, 1, 12, 10, 00, 0),
            stepsize=datetime.timedelta(seconds=5))

        unit_under_test = self.create_unit_under_test()

        unit_under_test.wait()

        assert self.mock_sleep.call_count == (5*60+30)/self.waiting_time_in_seconds

    def test_wait_switch_is_off(self, mocker):
        self.mock_dependencies(mocker)

        self.mock_connector.switched_on.side_effect = 200 * [False]
        self.mock_get_datetime_now.side_effect = self._generate_datetimes(
            start_datetime=datetime.datetime(2022, 1, 1, 12, 00, 00, 0),
            end_datetime=datetime.datetime(2022, 1, 1, 12, 10, 00, 0),
            stepsize=datetime.timedelta(seconds=5))

        unit_under_test = self.create_unit_under_test()

        unit_under_test.wait()

        assert self.mock_sleep.call_count == (5*60)/self.waiting_time_in_seconds

    def test_wait_switch_is_off_switches_on_while_waiting(self, mocker):
        self.mock_dependencies(mocker)

        self.mock_connector.switched_on.side_effect = 20 * [False] + [True]
        self.mock_get_datetime_now.side_effect = self._generate_datetimes(
            start_datetime=datetime.datetime(2022, 1, 1, 12, 00, 00, 0),
            end_datetime=datetime.datetime(2022, 1, 1, 12, 10, 00, 0),
            stepsize=datetime.timedelta(seconds=5))

        unit_under_test = self.create_unit_under_test()

        unit_under_test.wait()

        assert self.mock_sleep.call_count == 20
