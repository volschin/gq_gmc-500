"""The GQ GMC-500 Radiation Monitor integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from typing import TypeAlias

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN, CONF_PORT, DEFAULT_PORT
from .coordinator import GMCCoordinator
from .server import GMCServer

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


@dataclass
class GMCRuntimeData:
    """Runtime data for a GMC-500 config entry."""

    coordinator: GMCCoordinator
    server: GMCServer


if TYPE_CHECKING:
    GMCConfigEntry: TypeAlias = ConfigEntry[GMCRuntimeData]
else:
    GMCConfigEntry = ConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: GMCConfigEntry) -> bool:
    """Set up GMC-500 from a config entry."""
    coordinator = GMCCoordinator(hass)
    port = entry.options.get(CONF_PORT, entry.data.get(CONF_PORT, DEFAULT_PORT))

    # Restore registered devices from config entry data
    for device_id, name in entry.data.get("registered_devices", {}).items():
        aid, gid = device_id.split("_", 1)
        coordinator.register_device(aid, gid, name)

    async def handle_data(data: dict[str, Any]) -> None:
        """Handle incoming data from a GMC-500 device."""
        aid = data["AID"]
        gid = data["GID"]

        if coordinator.is_device_ignored(aid, gid):
            return

        if not coordinator.is_device_known(aid, gid):
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": "discovery"},
                    data={
                        "aid": aid,
                        "gid": gid,
                        "cpm": data.get("CPM"),
                    },
                )
            )
            coordinator.process_data(data)
            return

        coordinator.process_data(data)

    server = GMCServer(port=port, data_callback=handle_data)
    try:
        await server.start()
    except OSError as err:
        ir.async_create_issue(
            hass,
            DOMAIN,
            "port_in_use",
            is_fixable=True,
            is_persistent=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key="port_in_use",
            translation_placeholders={"port": str(port)},
        )
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="port_unavailable",
            translation_placeholders={"port": str(port)},
        ) from err

    ir.async_delete_issue(hass, DOMAIN, "port_in_use")

    entry.runtime_data = GMCRuntimeData(coordinator=coordinator, server=server)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(
        entry.add_update_listener(_async_update_listener)
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: GMCConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.server.stop()
    return unload_ok


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    entry: GMCConfigEntry,
    device_entry: dr.DeviceEntry,
) -> bool:
    """Allow manual removal of a device from the device registry.

    Returns False if the device is still actively sending data.
    """
    coordinator = entry.runtime_data.coordinator
    for identifier in device_entry.identifiers:
        if identifier[0] == DOMAIN:
            device_id = identifier[1]
            return device_id not in coordinator.devices
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: GMCConfigEntry
) -> None:
    """Handle options update — restart integration."""
    await hass.config_entries.async_reload(entry.entry_id)
