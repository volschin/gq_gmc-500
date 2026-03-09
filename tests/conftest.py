"""Test fixtures for GMC-500 integration."""

import sys
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Mock homeassistant modules globally so that importing any submodule of
# custom_components.gmc500 (which triggers __init__.py) does not fail.
# Individual test files may override specific attributes as needed.
# ---------------------------------------------------------------------------

_ha = MagicMock()

# config_entries needs real base classes for config_flow.py to inherit from
_ha_config_entries = MagicMock()


class _MockConfigFlow:
    """Mock ConfigFlow base class."""

    def __init_subclass__(cls, domain=None, **kwargs):
        super().__init_subclass__(**kwargs)

    def async_show_form(self, **kwargs):
        return {"type": "form", **kwargs}

    def async_create_entry(self, **kwargs):
        return {"type": "create_entry", **kwargs}

    async def async_set_unique_id(self, unique_id):
        self._unique_id = unique_id

    def _abort_if_unique_id_configured(self):
        pass


class _MockOptionsFlow:
    """Mock OptionsFlow base class."""

    def async_show_form(self, **kwargs):
        return {"type": "form", **kwargs}

    def async_create_entry(self, **kwargs):
        return {"type": "create_entry", **kwargs}


_ha_config_entries.ConfigFlow = _MockConfigFlow
_ha_config_entries.OptionsFlow = _MockOptionsFlow
_ha_config_entries.ConfigFlowResult = dict
_ha_config_entries.ConfigEntry = MagicMock

_ha_const = MagicMock()
_ha_const.Platform = MagicMock()
_ha_const.Platform.SENSOR = "sensor"

_ha_core = MagicMock()
_ha_core.callback = lambda f: f  # passthrough decorator
_ha_core.HomeAssistant = MagicMock

_ha_entity = MagicMock()
_ha_entity.DeviceInfo = dict

_ha_sensor = MagicMock()
_ha_sensor.SensorDeviceClass = MagicMock()
_ha_sensor.SensorDeviceClass.TEMPERATURE = "temperature"
_ha_sensor.SensorDeviceClass.HUMIDITY = "humidity"
_ha_sensor.SensorDeviceClass.ATMOSPHERIC_PRESSURE = "atmospheric_pressure"
_ha_sensor.SensorEntity = type("SensorEntity", (), {})
_ha_sensor.SensorStateClass = MagicMock()
_ha_sensor.SensorStateClass.MEASUREMENT = "measurement"

class _ConfigEntryNotReady(Exception):
    def __init__(self, *args, translation_domain=None, translation_key=None,
                 translation_placeholders=None, **kwargs):
        super().__init__(*args)
        self.translation_domain = translation_domain
        self.translation_key = translation_key
        self.translation_placeholders = translation_placeholders

_ha_exceptions = MagicMock()
_ha_exceptions.ConfigEntryNotReady = _ConfigEntryNotReady

_ha_issue_registry = MagicMock()
_ha_issue_registry.IssueSeverity = MagicMock()
_ha_issue_registry.IssueSeverity.ERROR = "error"

_ha_helpers = MagicMock()
_ha_helpers.issue_registry = _ha_issue_registry

sys.modules.setdefault("homeassistant", _ha)
sys.modules.setdefault("homeassistant.config_entries", _ha_config_entries)
sys.modules.setdefault("homeassistant.const", _ha_const)
sys.modules.setdefault("homeassistant.core", _ha_core)
sys.modules.setdefault("homeassistant.exceptions", _ha_exceptions)
sys.modules.setdefault("homeassistant.helpers", _ha_helpers)
sys.modules.setdefault("homeassistant.helpers.entity", _ha_entity)
sys.modules.setdefault("homeassistant.helpers.entity_platform", MagicMock())
sys.modules.setdefault("homeassistant.helpers.issue_registry", _ha_issue_registry)
sys.modules.setdefault("homeassistant.components", MagicMock())
sys.modules.setdefault("homeassistant.components.sensor", _ha_sensor)


@pytest.fixture
def mock_setup_entry():
    """Mock setting up a config entry."""
    with patch(
        "custom_components.gmc500.async_setup_entry",
        return_value=True,
    ) as mock:
        yield mock
