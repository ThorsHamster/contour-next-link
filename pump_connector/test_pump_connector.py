import pytest
import datetime

from pump_connector import PumpConnector


class MockConnector:
    def switched_on(self):
        return True


@pytest.fixture
def unit_under_test(mocker):
    mocker.patch('pump_connector.helper.get_datetime_now',
                 return_value=datetime.datetime(2022, 1, 1, 12, 00, 00, 0))
    return PumpConnector(connector=MockConnector())


def test_wait(unit_under_test, mocker):
    mocker.patch('pump_connector.helper.get_datetime_now',
                 return_value=[datetime.datetime(2022, 1, 1, 12, 00, 00, 0),
                               datetime.datetime(2022, 1, 1, 12, 5, 00, 0),
                               datetime.datetime(2022, 1, 1, 12, 10, 00, 0),
                               datetime.datetime(2022, 1, 1, 12, 15, 00, 0),
                               datetime.datetime(2022, 1, 1, 12, 20, 00, 0),
                               datetime.datetime(2022, 1, 1, 12, 30, 00, 0)])
    mock_sleep = mocker.patch('time.sleep')

    #unit_under_test.wait()

    assert mock_sleep.call_count == 4
