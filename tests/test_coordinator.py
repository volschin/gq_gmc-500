"""Tests for the GMC-500 coordinator."""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta

from custom_components.gmc500.coordinator import GMCCoordinator
from custom_components.gmc500.const import AVAILABILITY_TIMEOUT


@pytest.fixture
def coordinator():
    """Create a coordinator instance."""
    hass = MagicMock()
    hass.bus = MagicMock()
    coord = GMCCoordinator(hass)
    return coord


def _valid_data():
    """Return valid GMC-500 data."""
    return {
        "AID": "0230111",
        "GID": "0034021",
        "CPM": 15.0,
        "ACPM": 13.2,
        "uSV": 0.075,
    }


def test_process_data_stores_device_data(coordinator):
    """Test that incoming data is stored per device."""
    coordinator.process_data(_valid_data())
    device_id = "0230111_0034021"
    assert device_id in coordinator.devices
    assert coordinator.devices[device_id]["CPM"] == 15.0


def test_process_data_updates_last_seen(coordinator):
    """Test that last_seen timestamp is updated."""
    coordinator.process_data(_valid_data())
    device_id = "0230111_0034021"
    assert "last_seen" in coordinator.devices[device_id]


def test_is_device_known_false_initially(coordinator):
    """Test that unknown device returns False."""
    assert not coordinator.is_device_known("0230111", "0034021")


def test_is_device_known_true_after_registration(coordinator):
    """Test that known device returns True after registration."""
    coordinator.register_device("0230111", "0034021", "My Counter")
    assert coordinator.is_device_known("0230111", "0034021")


def test_device_availability_true_when_recent(coordinator):
    """Test device is available when recently seen."""
    coordinator.register_device("0230111", "0034021", "My Counter")
    coordinator.process_data(_valid_data())
    assert coordinator.is_device_available("0230111_0034021")


def test_device_availability_false_when_stale(coordinator):
    """Test device is unavailable when not seen for too long."""
    coordinator.register_device("0230111", "0034021", "My Counter")
    coordinator.process_data(_valid_data())
    coordinator.devices["0230111_0034021"]["last_seen"] = (
        datetime.now() - timedelta(seconds=AVAILABILITY_TIMEOUT + 1)
    )
    assert not coordinator.is_device_available("0230111_0034021")


def test_ignored_device_not_processed(coordinator):
    """Test that data from ignored devices is not processed."""
    coordinator.ignore_device("0230111", "0034021")
    coordinator.process_data(_valid_data())
    assert "0230111_0034021" not in coordinator.devices


@pytest.mark.asyncio
async def test_forward_to_gmcmap_success():
    """Test successful forwarding to gmcmap.com."""
    hass = MagicMock()
    coordinator = GMCCoordinator(hass)

    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        await coordinator.forward_to_gmcmap(_valid_data())


@pytest.mark.asyncio
async def test_forward_to_gmcmap_retries_on_failure():
    """Test that forwarding retries on failure."""
    hass = MagicMock()
    coordinator = GMCCoordinator(hass)

    mock_resp = AsyncMock()
    mock_resp.status = 500
    mock_resp.text = AsyncMock(return_value="Server Error")
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await coordinator.forward_to_gmcmap(_valid_data())
    assert mock_session.get.call_count == 3
