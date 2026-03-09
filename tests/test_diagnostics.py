"""Tests for GMC-500 diagnostics."""

import sys
from datetime import datetime
from unittest.mock import MagicMock

import pytest

# Re-use mocks already registered via conftest.py
sys.modules.setdefault("homeassistant.components.diagnostics", MagicMock())

from custom_components.gmc500.diagnostics import async_get_config_entry_diagnostics  # noqa: E402
from custom_components.gmc500.coordinator import GMCCoordinator  # noqa: E402


def _make_coordinator_with_data():
    hass = MagicMock()
    coordinator = GMCCoordinator(hass)
    coordinator.register_device("AID1", "GID1", "My Counter")
    coordinator.devices["AID1_GID1"] = {
        "AID": "AID1", "GID": "GID1", "CPM": 15.0,
        "last_seen": datetime(2026, 3, 9, 10, 0, 0),
    }
    return coordinator


class TestDiagnostics:
    @pytest.mark.asyncio
    async def test_returns_dict(self):
        """Diagnostics returns a dict."""
        hass = MagicMock()
        entry = MagicMock()
        entry.data = {"port": 8080}
        coordinator = _make_coordinator_with_data()
        entry.runtime_data = MagicMock()
        entry.runtime_data.coordinator = coordinator

        result = await async_get_config_entry_diagnostics(hass, entry)

        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_contains_port(self):
        """Diagnostics includes the configured port."""
        hass = MagicMock()
        entry = MagicMock()
        entry.data = {"port": 8080}
        coordinator = _make_coordinator_with_data()
        entry.runtime_data = MagicMock()
        entry.runtime_data.coordinator = coordinator

        result = await async_get_config_entry_diagnostics(hass, entry)

        assert result["entry"]["port"] == 8080

    @pytest.mark.asyncio
    async def test_contains_device_ids(self):
        """Diagnostics lists registered device IDs."""
        hass = MagicMock()
        entry = MagicMock()
        entry.data = {"port": 8080}
        coordinator = _make_coordinator_with_data()
        entry.runtime_data = MagicMock()
        entry.runtime_data.coordinator = coordinator

        result = await async_get_config_entry_diagnostics(hass, entry)

        assert "AID1_GID1" in result["devices"]

    @pytest.mark.asyncio
    async def test_last_seen_is_serializable(self):
        """Diagnostics converts datetime last_seen to string."""
        hass = MagicMock()
        entry = MagicMock()
        entry.data = {"port": 8080}
        coordinator = _make_coordinator_with_data()
        entry.runtime_data = MagicMock()
        entry.runtime_data.coordinator = coordinator

        result = await async_get_config_entry_diagnostics(hass, entry)

        last_seen = result["devices"]["AID1_GID1"].get("last_seen")
        assert isinstance(last_seen, str)

    @pytest.mark.asyncio
    async def test_registered_devices_listed(self):
        """Diagnostics includes registered device keys."""
        hass = MagicMock()
        entry = MagicMock()
        entry.data = {"port": 8080}
        coordinator = _make_coordinator_with_data()
        entry.runtime_data = MagicMock()
        entry.runtime_data.coordinator = coordinator

        result = await async_get_config_entry_diagnostics(hass, entry)

        assert "AID1_GID1" in result["registered_devices"]

    @pytest.mark.asyncio
    async def test_ignored_devices_listed(self):
        """Diagnostics includes ignored device list."""
        hass = MagicMock()
        entry = MagicMock()
        entry.data = {"port": 8080}
        coordinator = _make_coordinator_with_data()
        coordinator.ignore_device("AID1", "GID1")
        entry.runtime_data = MagicMock()
        entry.runtime_data.coordinator = coordinator

        result = await async_get_config_entry_diagnostics(hass, entry)

        assert "AID1_GID1" in result["ignored_devices"]
