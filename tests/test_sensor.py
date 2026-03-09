"""Tests for GMC-500 sensor entities.

Since homeassistant is not installed in the dev environment, we mock the
homeassistant modules via sys.modules before importing sensor.py.
"""

import sys
from unittest.mock import MagicMock, patch
from datetime import datetime

import pytest

# ---------------------------------------------------------------------------
# Mock homeassistant modules so sensor.py can be imported without HA installed
# ---------------------------------------------------------------------------

_ha_sensor = MagicMock()
_ha_sensor.SensorDeviceClass = MagicMock()
_ha_sensor.SensorDeviceClass.TEMPERATURE = "temperature"
_ha_sensor.SensorDeviceClass.HUMIDITY = "humidity"
_ha_sensor.SensorDeviceClass.ATMOSPHERIC_PRESSURE = "atmospheric_pressure"
_ha_sensor.SensorEntity = type("SensorEntity", (), {})
_ha_sensor.SensorStateClass = MagicMock()
_ha_sensor.SensorStateClass.MEASUREMENT = "measurement"

_ha_config_entries = MagicMock()
_ha_core = MagicMock()
_ha_core.callback = lambda f: f  # passthrough decorator
_ha_entity = MagicMock()
_ha_entity.DeviceInfo = dict  # use dict as a stand-in for DeviceInfo
_ha_entity_platform = MagicMock()

sys.modules.setdefault("homeassistant", MagicMock())
sys.modules.setdefault("homeassistant.components", MagicMock())
sys.modules.setdefault("homeassistant.components.sensor", _ha_sensor)
sys.modules.setdefault("homeassistant.config_entries", _ha_config_entries)
sys.modules.setdefault("homeassistant.core", _ha_core)
sys.modules.setdefault("homeassistant.helpers", MagicMock())
sys.modules.setdefault("homeassistant.helpers.entity", _ha_entity)
sys.modules.setdefault("homeassistant.helpers.entity_platform", _ha_entity_platform)

from custom_components.gmc500.sensor import (  # noqa: E402
    GMCBaseSensor,
    GMCEnvironmentSensor,
    GMCRadiationSensor,
    GMCSensorDescription,
    SENSOR_DESCRIPTIONS,
    RADIATION_SENSORS,
    ENVIRONMENT_SENSORS,
    async_setup_entry,
)
from custom_components.gmc500.coordinator import GMCCoordinator  # noqa: E402
from custom_components.gmc500.const import DOMAIN  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_coordinator() -> GMCCoordinator:
    """Create a coordinator with a mock hass object."""
    hass = MagicMock()
    return GMCCoordinator(hass)


def _valid_data() -> dict:
    """Return valid device data."""
    return {
        "AID": "0230111",
        "GID": "0034021",
        "CPM": 15.0,
        "ACPM": 13.2,
        "uSV": 0.075,
    }


def _valid_data_with_env() -> dict:
    """Return valid device data including environment sensors."""
    data = _valid_data()
    data.update({"tmp": 22.5, "hmdt": 55.0, "ap": 1013.25})
    return data


AID = "0230111"
GID = "0034021"
DEVICE_ID = f"{AID}_{GID}"


# ---------------------------------------------------------------------------
# Tests: GMCRadiationSensor
# ---------------------------------------------------------------------------

class TestGMCRadiationSensor:
    """Tests for the radiation sensor."""

    def test_cpm_native_value(self):
        """CPM sensor returns correct value from coordinator data."""
        coordinator = _make_coordinator()
        coordinator.process_data(_valid_data())
        sensor = GMCRadiationSensor(
            coordinator, AID, GID, SENSOR_DESCRIPTIONS["CPM"]
        )
        assert sensor.native_value == 15.0

    def test_acpm_native_value(self):
        """ACPM sensor returns correct value."""
        coordinator = _make_coordinator()
        coordinator.process_data(_valid_data())
        sensor = GMCRadiationSensor(
            coordinator, AID, GID, SENSOR_DESCRIPTIONS["ACPM"]
        )
        assert sensor.native_value == 13.2

    def test_usv_native_value(self):
        """uSV sensor returns correct value."""
        coordinator = _make_coordinator()
        coordinator.process_data(_valid_data())
        sensor = GMCRadiationSensor(
            coordinator, AID, GID, SENSOR_DESCRIPTIONS["uSV"]
        )
        assert sensor.native_value == 0.075

    def test_native_value_none_when_no_device_data(self):
        """Sensor returns None when device has no data."""
        coordinator = _make_coordinator()
        sensor = GMCRadiationSensor(
            coordinator, AID, GID, SENSOR_DESCRIPTIONS["CPM"]
        )
        assert sensor.native_value is None


# ---------------------------------------------------------------------------
# Tests: GMCEnvironmentSensor
# ---------------------------------------------------------------------------

class TestGMCEnvironmentSensor:
    """Tests for the environment sensor."""

    def test_temperature_value(self):
        """Temperature sensor returns correct value when present."""
        coordinator = _make_coordinator()
        coordinator.process_data(_valid_data_with_env())
        sensor = GMCEnvironmentSensor(
            coordinator, AID, GID, SENSOR_DESCRIPTIONS["tmp"]
        )
        assert sensor.native_value == 22.5

    def test_humidity_value(self):
        """Humidity sensor returns correct value."""
        coordinator = _make_coordinator()
        coordinator.process_data(_valid_data_with_env())
        sensor = GMCEnvironmentSensor(
            coordinator, AID, GID, SENSOR_DESCRIPTIONS["hmdt"]
        )
        assert sensor.native_value == 55.0

    def test_returns_none_when_parameter_missing(self):
        """Environment sensor returns None when its parameter is missing."""
        coordinator = _make_coordinator()
        # Process data without environment parameters
        coordinator.process_data(_valid_data())
        sensor = GMCEnvironmentSensor(
            coordinator, AID, GID, SENSOR_DESCRIPTIONS["tmp"]
        )
        assert sensor.native_value is None

    def test_returns_none_when_no_device_data(self):
        """Environment sensor returns None when device has no data at all."""
        coordinator = _make_coordinator()
        sensor = GMCEnvironmentSensor(
            coordinator, AID, GID, SENSOR_DESCRIPTIONS["tmp"]
        )
        assert sensor.native_value is None


# ---------------------------------------------------------------------------
# Tests: Sensor attributes (unique_id, device_info, availability)
# ---------------------------------------------------------------------------

class TestSensorAttributes:
    """Tests for common sensor attributes."""

    def test_unique_id_format(self):
        """Sensor unique_id has the expected format."""
        coordinator = _make_coordinator()
        sensor = GMCRadiationSensor(
            coordinator, AID, GID, SENSOR_DESCRIPTIONS["CPM"]
        )
        assert sensor._attr_unique_id == f"{DOMAIN}_{AID}_{GID}_cpm"

    def test_unique_id_format_usv(self):
        """uSV sensor key is lowercased in unique_id."""
        coordinator = _make_coordinator()
        sensor = GMCRadiationSensor(
            coordinator, AID, GID, SENSOR_DESCRIPTIONS["uSV"]
        )
        assert sensor._attr_unique_id == f"{DOMAIN}_{AID}_{GID}_usv"

    def test_device_info_identifiers(self):
        """Device info contains correct identifiers."""
        coordinator = _make_coordinator()
        sensor = GMCRadiationSensor(
            coordinator, AID, GID, SENSOR_DESCRIPTIONS["CPM"]
        )
        info = sensor.device_info
        assert info["identifiers"] == {(DOMAIN, DEVICE_ID)}

    def test_device_info_manufacturer(self):
        """Device info has correct manufacturer."""
        coordinator = _make_coordinator()
        sensor = GMCRadiationSensor(
            coordinator, AID, GID, SENSOR_DESCRIPTIONS["CPM"]
        )
        info = sensor.device_info
        assert info["manufacturer"] == "GQ Electronics"

    def test_device_info_model(self):
        """Device info has correct model."""
        coordinator = _make_coordinator()
        sensor = GMCRadiationSensor(
            coordinator, AID, GID, SENSOR_DESCRIPTIONS["CPM"]
        )
        info = sensor.device_info
        assert info["model"] == "GMC-500"

    def test_device_info_name(self):
        """Device info name includes GID."""
        coordinator = _make_coordinator()
        sensor = GMCRadiationSensor(
            coordinator, AID, GID, SENSOR_DESCRIPTIONS["CPM"]
        )
        info = sensor.device_info
        assert info["name"] == f"GMC-500 {GID}"

    def test_available_true_when_coordinator_reports_available(self):
        """Availability tracks coordinator — available when device was seen."""
        coordinator = _make_coordinator()
        coordinator.process_data(_valid_data())
        sensor = GMCRadiationSensor(
            coordinator, AID, GID, SENSOR_DESCRIPTIONS["CPM"]
        )
        assert sensor.available is True

    def test_available_false_when_coordinator_reports_unavailable(self):
        """Availability tracks coordinator — unavailable when device not seen."""
        coordinator = _make_coordinator()
        sensor = GMCRadiationSensor(
            coordinator, AID, GID, SENSOR_DESCRIPTIONS["CPM"]
        )
        assert sensor.available is False

    def test_sensor_name(self):
        """Sensor name attribute is set from description."""
        coordinator = _make_coordinator()
        sensor = GMCRadiationSensor(
            coordinator, AID, GID, SENSOR_DESCRIPTIONS["CPM"]
        )
        assert sensor._attr_name == "CPM"

    def test_sensor_unit(self):
        """Sensor unit attribute is set from description."""
        coordinator = _make_coordinator()
        sensor = GMCEnvironmentSensor(
            coordinator, AID, GID, SENSOR_DESCRIPTIONS["tmp"]
        )
        assert sensor._attr_native_unit_of_measurement == "°C"

    def test_sensor_icon(self):
        """Radiation sensors have the radioactive icon."""
        coordinator = _make_coordinator()
        sensor = GMCRadiationSensor(
            coordinator, AID, GID, SENSOR_DESCRIPTIONS["CPM"]
        )
        assert sensor._attr_icon == "mdi:radioactive"


# ---------------------------------------------------------------------------
# Tests: async_setup_entry listener
# ---------------------------------------------------------------------------

class TestAsyncSetupEntry:
    """Tests for the async_setup_entry platform setup."""

    @pytest.mark.asyncio
    async def test_listener_creates_radiation_sensors_for_known_device(self):
        """Listener creates radiation sensors when a known device reports."""
        hass = MagicMock()
        coordinator = GMCCoordinator(hass)
        coordinator.register_device(AID, GID, "My Counter")

        entry = MagicMock()
        entry.entry_id = "test_entry"
        hass.data = {DOMAIN: {entry.entry_id: {"coordinator": coordinator}}}

        added_entities: list = []
        async_add_entities = MagicMock(side_effect=lambda e: added_entities.extend(e))

        await async_setup_entry(hass, entry, async_add_entities)

        # Simulate data arrival
        data = _valid_data()
        coordinator.process_data(data)

        assert len(added_entities) == len(RADIATION_SENSORS)
        assert all(
            isinstance(e, GMCRadiationSensor) for e in added_entities
        )

    @pytest.mark.asyncio
    async def test_listener_creates_env_sensors_when_present(self):
        """Listener creates environment sensors when env data is present."""
        hass = MagicMock()
        coordinator = GMCCoordinator(hass)
        coordinator.register_device(AID, GID, "My Counter")

        entry = MagicMock()
        entry.entry_id = "test_entry"
        hass.data = {DOMAIN: {entry.entry_id: {"coordinator": coordinator}}}

        added_entities: list = []
        async_add_entities = MagicMock(side_effect=lambda e: added_entities.extend(e))

        await async_setup_entry(hass, entry, async_add_entities)

        data = _valid_data_with_env()
        coordinator.process_data(data)

        radiation_count = len(RADIATION_SENSORS)
        env_count = len(ENVIRONMENT_SENSORS)
        assert len(added_entities) == radiation_count + env_count

    @pytest.mark.asyncio
    async def test_listener_ignores_unknown_device(self):
        """Listener does not create entities for unregistered devices."""
        hass = MagicMock()
        coordinator = GMCCoordinator(hass)
        # Device is NOT registered

        entry = MagicMock()
        entry.entry_id = "test_entry"
        hass.data = {DOMAIN: {entry.entry_id: {"coordinator": coordinator}}}

        async_add_entities = MagicMock()

        await async_setup_entry(hass, entry, async_add_entities)

        coordinator.process_data(_valid_data())

        async_add_entities.assert_not_called()

    @pytest.mark.asyncio
    async def test_listener_tracks_devices_only_once(self):
        """Listener does not re-create entities for already-tracked devices."""
        hass = MagicMock()
        coordinator = GMCCoordinator(hass)
        coordinator.register_device(AID, GID, "My Counter")

        entry = MagicMock()
        entry.entry_id = "test_entry"
        hass.data = {DOMAIN: {entry.entry_id: {"coordinator": coordinator}}}

        async_add_entities = MagicMock()

        await async_setup_entry(hass, entry, async_add_entities)

        coordinator.process_data(_valid_data())
        coordinator.process_data(_valid_data())

        assert async_add_entities.call_count == 1
