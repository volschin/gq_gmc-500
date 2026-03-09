"""Sensor entities for the GQ GMC-500 integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import GMCCoordinator

# Push-based integration — coordinator handles updates, no parallel polling needed
PARALLEL_UPDATES = 0


@dataclass
class GMCSensorDescription:
    """Describe a GMC-500 sensor."""

    key: str
    name: str
    unit: str
    device_class: SensorDeviceClass | None = None
    icon: str | None = None


SENSOR_DESCRIPTIONS: dict[str, GMCSensorDescription] = {
    "CPM": GMCSensorDescription(
        key="CPM", name="CPM", unit="CPM", icon="mdi:radioactive"
    ),
    "ACPM": GMCSensorDescription(
        key="ACPM", name="Average CPM", unit="CPM", icon="mdi:radioactive"
    ),
    "uSV": GMCSensorDescription(
        key="uSV", name="Dose Rate", unit="µSv/h", icon="mdi:radioactive"
    ),
    "tmp": GMCSensorDescription(
        key="tmp",
        name="Temperature",
        unit="°C",
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    "hmdt": GMCSensorDescription(
        key="hmdt",
        name="Humidity",
        unit="%",
        device_class=SensorDeviceClass.HUMIDITY,
    ),
    "ap": GMCSensorDescription(
        key="ap",
        name="Atmospheric Pressure",
        unit="hPa",
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
    ),
}

RADIATION_SENSORS = ["CPM", "ACPM", "uSV"]
ENVIRONMENT_SENSORS = ["tmp", "hmdt", "ap"]


class GMCBaseSensor(SensorEntity):
    """Base class for GMC-500 sensors."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_has_entity_name = True
    _remove_listener: Callable[[], None] | None = None

    def __init__(
        self,
        coordinator: GMCCoordinator,
        aid: str,
        gid: str,
        description: GMCSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        self._coordinator = coordinator
        self._aid = aid
        self._gid = gid
        self._device_id = f"{aid}_{gid}"
        self._description = description

        self._attr_unique_id = f"{DOMAIN}_{aid}_{gid}_{description.key.lower()}"
        self._attr_name = description.name
        self._attr_native_unit_of_measurement = description.unit
        self._attr_device_class = description.device_class
        self._attr_icon = description.icon

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=f"GMC-500 {self._gid}",
            manufacturer="GQ Electronics",
            model="GMC-500",
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._coordinator.is_device_available(self._device_id)

    @property
    def native_value(self) -> float | None:
        """Return the sensor value."""
        device_data = self._coordinator.devices.get(self._device_id)
        if device_data is None:
            return None
        return device_data.get(self._description.key)

    async def async_added_to_hass(self) -> None:
        """Register coordinator listener when added to Home Assistant."""
        self._remove_listener = self._coordinator.add_listener(
            self._handle_coordinator_update
        )

    async def async_will_remove_from_hass(self) -> None:
        """Unregister coordinator listener when removed from Home Assistant."""
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None

    @callback
    def _handle_coordinator_update(self, device_id: str, data: dict) -> None:
        """Write HA state when coordinator has new data for this device."""
        if device_id == self._device_id:
            self.async_write_ha_state()


class GMCRadiationSensor(GMCBaseSensor):
    """Sensor for radiation measurements (CPM, ACPM, µSv/h)."""


class GMCEnvironmentSensor(GMCBaseSensor):
    """Sensor for environmental measurements (temperature, humidity, pressure)."""


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GMC-500 sensors from a config entry."""
    coordinator: GMCCoordinator = entry.runtime_data.coordinator
    tracked_devices: set[str] = set()

    @callback
    def _async_handle_data(device_id: str, data: dict[str, Any]) -> None:
        """Handle new data from a device."""
        if device_id in tracked_devices:
            return

        aid = data["AID"]
        gid = data["GID"]

        if not coordinator.is_device_known(aid, gid):
            return

        tracked_devices.add(device_id)
        entities: list[SensorEntity] = []

        for key in RADIATION_SENSORS:
            entities.append(
                GMCRadiationSensor(coordinator, aid, gid, SENSOR_DESCRIPTIONS[key])
            )

        for key in ENVIRONMENT_SENSORS:
            if key in data:
                entities.append(
                    GMCEnvironmentSensor(
                        coordinator, aid, gid, SENSOR_DESCRIPTIONS[key]
                    )
                )

        async_add_entities(entities)

    coordinator.add_listener(_async_handle_data)
