import pytest
import datetime

from pump_connector import PumpConnector


class MockConnector:
    def switched_on(self):
        return True


class TestPumpConnector:

    @staticmethod
    def create_unit_under_test():
        return PumpConnector(connector=MockConnector())

    def mock_dependencies(self, mocker):
        # pylint: disable=attribute-defined-outside-init
        self.mock_sleep = mocker.patch("pump_connector.pump_connector.time.sleep")
        self.mock_get_datetime_now = mocker.patch("pump_connector.pump_connector.get_datetime_now")
        # pylint: enable=attribute-defined-outside-init

    def test_wait(self, mocker):
        self.mock_dependencies(mocker)

        self.mock_get_datetime_now.side_effect = [datetime.datetime(2022, 1, 1, 12, 00, 00, 0),  # init of class
                                                  datetime.datetime(2022, 1, 1, 12, 00, 00, 0),  # first call of wait
                                                  datetime.datetime(2022, 1, 1, 12, 00, 5, 0),
                                                  datetime.datetime(2022, 1, 1, 12, 00, 7, 0),
                                                  datetime.datetime(2022, 1, 1, 12, 5, 30, 0),
                                                  datetime.datetime(2022, 1, 1, 12, 10, 00, 0)]

        unit_under_test = self.create_unit_under_test()
        unit_under_test.wait()

        assert unit_under_test._connection_timestamp == datetime.datetime(2022, 1, 1, 12, 00, 00, 0)
        assert self.mock_sleep.call_count == 2
