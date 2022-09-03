import pydantic
import datetime

from homeassistant_api import Client


class HomeAssistantUploader:
    def __init__(self, token, ip, port):
        self._token = token
        self._api_url = "http://" + str(ip) + ":" + str(port) + "/api"

        assert token is not None
        assert ip is not None
        assert port is not None

        self._client = Client(self._api_url, token)

    def update_states(self, medtronic_pump_status):
        if self._is_data_valid(medtronic_pump_status):
            self._update_state(entity_id="sensor.minimed_bgl", state=medtronic_pump_status.sensorBGL)
            self._update_state(entity_id="sensor.minimed_trend", state=medtronic_pump_status.trendArrow)
            self._update_state(entity_id="sensor.minimed_active_insulin", state=medtronic_pump_status.activeInsulin)
            self._update_state(entity_id="sensor.minimed_current_basal_rate",
                               state=medtronic_pump_status.currentBasalRate)
            self._update_state(entity_id="sensor.minimed_temp_basal_rate", state=medtronic_pump_status.tempBasalRate)
            self._update_state(entity_id="sensor.minimed_temp_basal_rate_percentage",
                               state=medtronic_pump_status.tempBasalPercentage)
            self._update_state(entity_id="sensor.minimed_pump_battery_level",
                               state=medtronic_pump_status.batteryLevelPercentage)
            self._update_state(entity_id="sensor.minimed_insulin_units_remaining",
                               state=medtronic_pump_status.insulinUnitsRemaining)
            self.update_timestamp(state=str(medtronic_pump_status.sensorBGLTimestamp.strftime("%H:%M:%S %d.%m.%Y")))
        else:
            self.update_status("Invalid data.")
            self.update_timestamp(datetime.datetime.now().strftime("%H:%M:%S %d.%m.%Y"))

    @staticmethod
    def _is_data_valid(medtronic_pump_status) -> bool:
        invalid_sensor_values = [0, 770]
        return str(medtronic_pump_status.sensorBGLTimestamp.strftime(
            "%d.%m.%Y")) != "01.01.1970" and medtronic_pump_status.sensorBGL not in invalid_sensor_values

    def _update_state(self, entity_id, state):
        try:
            self._client.set_state(entity_id=entity_id, state=str(state))
        except pydantic.error_wrappers.ValidationError:
            pass

    def update_status(self, state):
        self._update_state(entity_id="sensor.minimed_status", state=str(state))

    def update_timestamp(self, state):
        self._update_state(entity_id="sensor.minimed_update_timestamp", state=str(state))

    def update_event(self, state):
        self._update_state(entity_id="sensor.minimed_message", state=str(state))
