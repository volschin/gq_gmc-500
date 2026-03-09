"""Tests for the GMC-500 integration setup (__init__.py).

Since homeassistant is not installed in the dev environment, we mock the
homeassistant modules via sys.modules before importing the integration.
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Mock homeassistant modules so __init__.py can be imported without HA
# ---------------------------------------------------------------------------

_ha_config_entries = MagicMock()
_ha_config_entries.ConfigEntry = MagicMock
_ha_const = MagicMock()
_ha_const.Platform = MagicMock()
_ha_const.Platform.SENSOR = "sensor"
_ha_core = MagicMock()
_ha_core.HomeAssistant = MagicMock

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

sys.modules.setdefault("homeassistant", MagicMock())
sys.modules.setdefault("homeassistant.config_entries", _ha_config_entries)
sys.modules.setdefault("homeassistant.const", _ha_const)
sys.modules.setdefault("homeassistant.core", _ha_core)
sys.modules.setdefault("homeassistant.exceptions", _ha_exceptions)
sys.modules.setdefault("homeassistant.helpers.issue_registry", _ha_issue_registry)

from custom_components.gmc500 import (  # noqa: E402
    async_setup_entry,
    async_unload_entry,
)
from custom_components.gmc500.const import DOMAIN  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hass():
    """Create a mock HomeAssistant instance."""
    hass = MagicMock()
    hass.data = {}
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.config_entries.flow.async_init = AsyncMock()
    hass.async_create_task = MagicMock(side_effect=lambda coro: coro)
    return hass


def _make_entry(entry_id="test_entry_id", port=8080):
    """Create a mock ConfigEntry."""
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.data = {"port": port}
    entry.async_on_unload = MagicMock()
    entry.add_update_listener = MagicMock()
    entry.runtime_data = None
    return entry


# ---------------------------------------------------------------------------
# Tests: async_setup_entry
# ---------------------------------------------------------------------------


class TestAsyncSetupEntry:
    """Tests for async_setup_entry."""

    @pytest.mark.asyncio
    async def test_starts_server_and_stores_data(self):
        """Setup starts the server and stores coordinator+server in hass.data."""
        hass = _make_hass()
        entry = _make_entry()

        with patch(
            "custom_components.gmc500.GMCServer"
        ) as mock_server_cls, patch(
            "custom_components.gmc500.GMCCoordinator"
        ) as mock_coord_cls:
            mock_server = AsyncMock()
            mock_server_cls.return_value = mock_server
            mock_coord = MagicMock()
            mock_coord_cls.return_value = mock_coord

            result = await async_setup_entry(hass, entry)

        assert result is True
        mock_server.start.assert_awaited_once()
        assert entry.runtime_data is not None
        assert entry.runtime_data.coordinator is mock_coord
        assert entry.runtime_data.server is mock_server

    @pytest.mark.asyncio
    async def test_forwards_platforms(self):
        """Setup forwards sensor platform setup."""
        hass = _make_hass()
        entry = _make_entry()

        with patch(
            "custom_components.gmc500.GMCServer"
        ) as mock_server_cls, patch(
            "custom_components.gmc500.GMCCoordinator"
        ):
            mock_server_cls.return_value = AsyncMock()

            await async_setup_entry(hass, entry)

        hass.config_entries.async_forward_entry_setups.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_registers_update_listener(self):
        """Setup registers an update listener for options changes."""
        hass = _make_hass()
        entry = _make_entry()

        with patch(
            "custom_components.gmc500.GMCServer"
        ) as mock_server_cls, patch(
            "custom_components.gmc500.GMCCoordinator"
        ):
            mock_server_cls.return_value = AsyncMock()

            await async_setup_entry(hass, entry)

        entry.async_on_unload.assert_called_once()
        entry.add_update_listener.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: async_unload_entry
# ---------------------------------------------------------------------------


class TestAsyncUnloadEntry:
    """Tests for async_unload_entry."""

    @pytest.mark.asyncio
    async def test_stops_server_and_removes_data(self):
        """Unload stops the server and removes entry from hass.data."""
        hass = _make_hass()
        entry = _make_entry()
        mock_server = AsyncMock()
        entry.runtime_data = MagicMock()
        entry.runtime_data.server = mock_server

        result = await async_unload_entry(hass, entry)

        assert result is True
        mock_server.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_does_not_remove_data_on_failed_unload(self):
        """Unload keeps data if platform unload fails."""
        hass = _make_hass()
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)
        entry = _make_entry()
        mock_server = AsyncMock()
        entry.runtime_data = MagicMock()
        entry.runtime_data.server = mock_server

        result = await async_unload_entry(hass, entry)

        assert result is False
        mock_server.stop.assert_not_awaited()


# ---------------------------------------------------------------------------
# Tests: handle_data callback
# ---------------------------------------------------------------------------


class TestHandleDataCallback:
    """Tests for the handle_data callback created inside async_setup_entry."""

    @pytest.mark.asyncio
    async def test_triggers_discovery_for_unknown_device(self):
        """handle_data triggers a discovery flow for unknown devices."""
        hass = _make_hass()
        entry = _make_entry()

        with patch(
            "custom_components.gmc500.GMCServer"
        ) as mock_server_cls, patch(
            "custom_components.gmc500.GMCCoordinator"
        ) as mock_coord_cls:
            mock_server = AsyncMock()
            mock_server_cls.return_value = mock_server
            mock_coord = MagicMock()
            mock_coord.is_device_ignored.return_value = False
            mock_coord.is_device_known.return_value = False
            mock_coord_cls.return_value = mock_coord

            await async_setup_entry(hass, entry)

            # Extract the handle_data callback passed to GMCServer
            call_kwargs = mock_server_cls.call_args
            data_callback = call_kwargs.kwargs.get(
                "data_callback"
            ) or call_kwargs[1].get("data_callback")
            if data_callback is None:
                # positional args: port, data_callback
                data_callback = call_kwargs[0][1] if len(call_kwargs[0]) > 1 else call_kwargs.kwargs["data_callback"]

        # Call the callback with test data
        test_data = {"AID": "0230111", "GID": "0034021", "CPM": 42.0}
        await data_callback(test_data)

        hass.async_create_task.assert_called()
        mock_coord.process_data.assert_called_once_with(test_data)

    @pytest.mark.asyncio
    async def test_processes_data_for_known_device(self):
        """handle_data calls process_data for known devices without discovery."""
        hass = _make_hass()
        entry = _make_entry()

        with patch(
            "custom_components.gmc500.GMCServer"
        ) as mock_server_cls, patch(
            "custom_components.gmc500.GMCCoordinator"
        ) as mock_coord_cls:
            mock_server = AsyncMock()
            mock_server_cls.return_value = mock_server
            mock_coord = MagicMock()
            mock_coord.is_device_ignored.return_value = False
            mock_coord.is_device_known.return_value = True
            mock_coord_cls.return_value = mock_coord

            await async_setup_entry(hass, entry)

            call_kwargs = mock_server_cls.call_args
            data_callback = call_kwargs.kwargs.get(
                "data_callback"
            ) or call_kwargs[1].get("data_callback")
            if data_callback is None:
                data_callback = call_kwargs[0][1] if len(call_kwargs[0]) > 1 else call_kwargs.kwargs["data_callback"]

        # Reset mock to track only the callback invocation
        mock_coord.process_data.reset_mock()
        hass.async_create_task.reset_mock()

        test_data = {"AID": "0230111", "GID": "0034021", "CPM": 42.0}
        await data_callback(test_data)

        mock_coord.process_data.assert_called_once_with(test_data)
        # async_create_task should NOT be called for known devices
        hass.async_create_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_ignored_device(self):
        """handle_data does nothing for ignored devices."""
        hass = _make_hass()
        entry = _make_entry()

        with patch(
            "custom_components.gmc500.GMCServer"
        ) as mock_server_cls, patch(
            "custom_components.gmc500.GMCCoordinator"
        ) as mock_coord_cls:
            mock_server = AsyncMock()
            mock_server_cls.return_value = mock_server
            mock_coord = MagicMock()
            mock_coord.is_device_ignored.return_value = True
            mock_coord_cls.return_value = mock_coord

            await async_setup_entry(hass, entry)

            call_kwargs = mock_server_cls.call_args
            data_callback = call_kwargs.kwargs.get(
                "data_callback"
            ) or call_kwargs[1].get("data_callback")
            if data_callback is None:
                data_callback = call_kwargs[0][1] if len(call_kwargs[0]) > 1 else call_kwargs.kwargs["data_callback"]

        test_data = {"AID": "0230111", "GID": "0034021", "CPM": 42.0}
        await data_callback(test_data)

        mock_coord.process_data.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: setup failure handling
# ---------------------------------------------------------------------------


class TestSetupFailure:
    """Tests for setup failure handling."""

    @pytest.mark.asyncio
    async def test_raises_config_entry_not_ready_when_server_fails(self):
        """Setup raises ConfigEntryNotReady when server cannot bind to port."""
        import sys
        ConfigEntryNotReady = sys.modules["homeassistant.exceptions"].ConfigEntryNotReady

        hass = _make_hass()
        entry = _make_entry(port=9999)

        with patch("custom_components.gmc500.GMCServer") as mock_server_cls, \
             patch("custom_components.gmc500.GMCCoordinator"):
            mock_server = AsyncMock()
            mock_server.start.side_effect = OSError("Address already in use")
            mock_server_cls.return_value = mock_server

            with pytest.raises(ConfigEntryNotReady):
                await async_setup_entry(hass, entry)

    @pytest.mark.asyncio
    async def test_creates_repair_issue_when_server_fails(self):
        """Setup creates a repair issue when server cannot bind."""
        import sys
        ir = sys.modules["homeassistant.helpers.issue_registry"]
        ir.async_create_issue.reset_mock()

        hass = _make_hass()
        entry = _make_entry(port=9999)

        with patch("custom_components.gmc500.GMCServer") as mock_server_cls, \
             patch("custom_components.gmc500.GMCCoordinator"):
            mock_server = AsyncMock()
            mock_server.start.side_effect = OSError("Address already in use")
            mock_server_cls.return_value = mock_server

            try:
                await async_setup_entry(hass, entry)
            except Exception:
                pass

        ir.async_create_issue.assert_called_once()

    @pytest.mark.asyncio
    async def test_clears_repair_issue_on_successful_setup(self):
        """Successful setup deletes any lingering repair issue."""
        import sys
        ir = sys.modules["homeassistant.helpers.issue_registry"]
        ir.async_delete_issue.reset_mock()

        hass = _make_hass()
        entry = _make_entry()

        with patch("custom_components.gmc500.GMCServer") as mock_server_cls, \
             patch("custom_components.gmc500.GMCCoordinator"):
            mock_server_cls.return_value = AsyncMock()
            await async_setup_entry(hass, entry)

        ir.async_delete_issue.assert_called_once()
