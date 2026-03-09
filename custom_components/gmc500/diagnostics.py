"""Diagnostics for the GQ GMC-500 integration."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import GMCConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: GMCConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data.coordinator

    devices: dict[str, Any] = {}
    for device_id, data in coordinator.devices.items():
        devices[device_id] = {
            k: str(v) if not isinstance(v, (int, float, str, bool, type(None))) else v
            for k, v in data.items()
        }

    return {
        "entry": {
            "port": entry.data.get("port"),
        },
        "devices": devices,
        "registered_devices": list(coordinator._registered_devices.keys()),
        "ignored_devices": list(coordinator._ignored_devices),
    }
