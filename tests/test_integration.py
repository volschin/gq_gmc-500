"""Integration tests for the full GMC-500 data flow."""

import socket

import pytest
import aiohttp
from unittest.mock import MagicMock

from custom_components.gmc500.server import GMCServer
from custom_components.gmc500.coordinator import GMCCoordinator


@pytest.fixture
def unused_tcp_port():
    """Find an unused TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.asyncio
async def test_full_flow_server_to_coordinator(unused_tcp_port):
    """Test complete data flow: HTTP request -> coordinator -> listener notification."""
    hass = MagicMock()
    hass.async_create_task = MagicMock(side_effect=lambda coro: coro)

    coordinator = GMCCoordinator(hass)
    coordinator.register_device("0230111", "0034021", "Test Counter")

    updates = []
    coordinator.add_listener(lambda device_id, data: updates.append((device_id, data)))

    server = GMCServer(
        port=unused_tcp_port,
        data_callback=lambda data: coordinator.process_data(data),
    )
    await server.start()

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"http://127.0.0.1:{unused_tcp_port}/log2.asp",
                params={
                    "AID": "0230111",
                    "GID": "0034021",
                    "CPM": "42",
                    "ACPM": "38.5",
                    "uSV": "0.285",
                    "tmp": "21.3",
                },
            ) as resp:
                assert resp.status == 200
                text = await resp.text()
                assert text == "OK.ERR0"

        assert len(updates) == 1
        device_id, data = updates[0]
        assert device_id == "0230111_0034021"
        assert data["CPM"] == 42.0
        assert data["ACPM"] == 38.5
        assert data["uSV"] == 0.285
        assert data["tmp"] == 21.3
        assert coordinator.is_device_available("0230111_0034021")
    finally:
        await server.stop()
