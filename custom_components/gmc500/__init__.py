"""The GQ GMC-500 Radiation Monitor integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

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


type GMCConfigEntry = ConfigEntry[GMCRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: GMCConfigEntry) -> bool:
    """Set up GMC-500 from a config entry."""
    coordinator = GMCCoordinator(hass)
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)

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
    await server.start()

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


async def _async_update_listener(
    hass: HomeAssistant, entry: GMCConfigEntry
) -> None:
    """Handle options update — restart integration."""
    await hass.config_entries.async_reload(entry.entry_id)
