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

    def _update_state(self, entity_id, state):
        try:
            self._client.set_state(entity_id=entity_id, state=str(state))
        except pydantic.error_wrappers.ValidationError:
            pass

    def update_bgl(self, state):
        self._update_state(entity_id="sensor.minimed_bgl", state=state)

    def update_trend(self, state):
        self._update_state(entity_id="sensor.minimed_trend", state=state)

    def update_active_insulin(self, state):
        self._update_state(entity_id="sensor.minimed_active_insulin", state=state)

    def update_current_basal_rate(self, state):
        self._update_state(entity_id="sensor.minimed_current_basal_rate", state=state)

    def update_temp_basal_rate(self, state):
        self._update_state(entity_id="sensor.minimed_temp_basal_rate", state=state)

    def update_temp_basal_rate_percentage(self, state):
        self._update_state(entity_id="sensor.minimed_temp_basal_rate_percentage", state=state)

    def update_pump_battery_level(self, state):
        self._update_state(entity_id="sensor.minimed_pump_battery_level", state=state)

    def update_insulin_units_remaining(self, state):
        self._update_state(entity_id="sensor.minimed_insulin_units_remaining", state=state)

    def update_status(self, state):
        self._update_state(entity_id="sensor.minimed_status", state=state)

    def update_timestamp(self, state):
        self._update_state(entity_id="sensor.minimed_update_timestamp", state=state)

    def update_event(self, state):
        self._update_state(entity_id="sensor.minimed_message", state=state)
