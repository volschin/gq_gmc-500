"""Coordinator for GMC-500 data management and gmcmap.com forwarding."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import aiohttp

from .const import (
    AVAILABILITY_TIMEOUT,
    GMCMAP_MAX_RETRIES,
    GMCMAP_TIMEOUT,
    GMCMAP_URL,
    PARAM_AID,
    PARAM_GID,
)

_LOGGER = logging.getLogger(__name__)


class GMCCoordinator:
    """Manage GMC-500 device data and gmcmap.com forwarding."""

    def __init__(self, hass: Any) -> None:
        """Initialize coordinator."""
        self.hass = hass
        self.devices: dict[str, dict[str, Any]] = {}
        self._registered_devices: dict[str, str] = {}
        self._ignored_devices: set[str] = set()
        self._listeners: list[Callable] = []
        self._availability_state: dict[str, bool] = {}

    def _device_id(self, aid: str, gid: str) -> str:
        """Build a unique device identifier from AID and GID."""
        return f"{aid}_{gid}"

    def register_device(self, aid: str, gid: str, name: str) -> None:
        """Register a device as known."""
        device_id = self._device_id(aid, gid)
        self._registered_devices[device_id] = name

    def is_device_known(self, aid: str, gid: str) -> bool:
        """Check whether a device has been registered."""
        return self._device_id(aid, gid) in self._registered_devices

    def ignore_device(self, aid: str, gid: str) -> None:
        """Mark a device as ignored so its data is discarded."""
        self._ignored_devices.add(self._device_id(aid, gid))

    def unignore_device(self, aid: str, gid: str) -> None:
        """Remove a device from the ignored set."""
        self._ignored_devices.discard(self._device_id(aid, gid))

    def is_device_ignored(self, aid: str, gid: str) -> bool:
        """Check whether a device is ignored."""
        return self._device_id(aid, gid) in self._ignored_devices

    def is_device_available(self, device_id: str) -> bool:
        """Return True if the device was seen within the availability window."""
        if device_id not in self.devices:
            return False
        last_seen = self.devices[device_id].get("last_seen")
        if last_seen is None:
            return False
        available = (datetime.now(tz=timezone.utc) - last_seen).total_seconds() <= AVAILABILITY_TIMEOUT

        prev = self._availability_state.get(device_id)
        if prev is True and not available:
            _LOGGER.info(
                "GMC-500 device %s is now unavailable (no data for 15 minutes)",
                device_id,
            )
            self._availability_state[device_id] = False

        return available

    def add_listener(self, listener: Callable) -> Callable:
        """Register a listener called on new data; returns a removal callback."""
        self._listeners.append(listener)

        def remove() -> None:
            self._listeners.remove(listener)

        return remove

    def process_data(self, data: dict[str, Any]) -> None:
        """Store incoming device data and trigger forwarding."""
        aid = data[PARAM_AID]
        gid = data[PARAM_GID]
        device_id = self._device_id(aid, gid)

        if device_id in self._ignored_devices:
            return

        was_available = self._availability_state.get(device_id)
        data["last_seen"] = datetime.now(tz=timezone.utc)
        self.devices[device_id] = data

        if was_available is False:
            _LOGGER.info("GMC-500 device %s/%s is now available", aid, gid)
        self._availability_state[device_id] = True

        for listener in self._listeners:
            listener(device_id, data)

        if device_id in self._registered_devices:
            self.hass.async_create_task(self.forward_to_gmcmap(data))

    async def forward_to_gmcmap(self, data: dict[str, Any]) -> None:
        """Forward device data to gmcmap.com with retry logic."""
        params = {k: v for k, v in data.items() if k != "last_seen"}

        async with aiohttp.ClientSession() as session:
            for attempt in range(GMCMAP_MAX_RETRIES):
                try:
                    async with session.get(
                        GMCMAP_URL,
                        params=params,
                        timeout=aiohttp.ClientTimeout(total=GMCMAP_TIMEOUT),
                    ) as resp:
                        if resp.status == 200:
                            return
                        body = await resp.text()
                        _LOGGER.warning(
                            "gmcmap.com returned status %s: %s",
                            resp.status,
                            body,
                        )
                except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                    _LOGGER.warning(
                        "gmcmap.com forwarding attempt %d failed: %s",
                        attempt + 1,
                        err,
                    )

                if attempt < GMCMAP_MAX_RETRIES - 1:
                    await asyncio.sleep(2**attempt)

        _LOGGER.warning(
            "gmcmap.com forwarding failed after %d attempts for device %s/%s",
            GMCMAP_MAX_RETRIES,
            data.get(PARAM_AID),
            data.get(PARAM_GID),
        )
