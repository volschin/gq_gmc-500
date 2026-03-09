"""Tests for the GMC-500 HTTP server."""

import socket

import pytest
import pytest_asyncio
import aiohttp

from custom_components.gmc500.server import GMCServer


@pytest.fixture
def unused_tcp_port():
    """Find an unused TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest_asyncio.fixture
async def gmc_server(unused_tcp_port):
    """Create and start a GMC server on a random port."""
    callback = []
    server = GMCServer(port=unused_tcp_port, data_callback=lambda data: callback.append(data))
    await server.start()
    yield server, unused_tcp_port, callback
    await server.stop()


@pytest.mark.asyncio
async def test_server_responds_ok(gmc_server):
    """Test that server responds with OK.ERR0 to valid request."""
    server, port, callback = gmc_server
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"http://127.0.0.1:{port}/log2.asp",
            params={
                "AID": "0230111",
                "GID": "0034021",
                "CPM": "15",
                "ACPM": "13.2",
                "uSV": "0.075",
            },
        ) as resp:
            assert resp.status == 200
            text = await resp.text()
            assert text == "OK.ERR0"
    assert len(callback) == 1
    assert callback[0]["AID"] == "0230111"
    assert callback[0]["CPM"] == 15.0


@pytest.mark.asyncio
async def test_server_handles_optional_params(gmc_server):
    """Test that optional params (tmp, hmdt, ap) are parsed when present."""
    server, port, callback = gmc_server
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"http://127.0.0.1:{port}/log2.asp",
            params={
                "AID": "0230111",
                "GID": "0034021",
                "CPM": "15",
                "ACPM": "13.2",
                "uSV": "0.075",
                "tmp": "22.5",
                "hmdt": "45.0",
                "ap": "1013.25",
            },
        ) as resp:
            assert resp.status == 200
    assert callback[0]["tmp"] == 22.5
    assert callback[0]["hmdt"] == 45.0
    assert callback[0]["ap"] == 1013.25


@pytest.mark.asyncio
async def test_server_rejects_missing_params(gmc_server):
    """Test that missing required params still returns OK.ERR0 but logs warning."""
    server, port, callback = gmc_server
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"http://127.0.0.1:{port}/log2.asp",
            params={"AID": "0230111"},
        ) as resp:
            assert resp.status == 200
            text = await resp.text()
            assert text == "OK.ERR0"
    assert len(callback) == 0


@pytest.mark.asyncio
async def test_server_handles_non_numeric_cpm(gmc_server):
    """Test that non-numeric CPM is rejected."""
    server, port, callback = gmc_server
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"http://127.0.0.1:{port}/log2.asp",
            params={
                "AID": "0230111",
                "GID": "0034021",
                "CPM": "abc",
                "ACPM": "13.2",
                "uSV": "0.075",
            },
        ) as resp:
            assert resp.status == 200
            text = await resp.text()
            assert text == "OK.ERR0"
    assert len(callback) == 0


@pytest.mark.asyncio
async def test_server_404_on_unknown_path(gmc_server):
    """Test that unknown paths return 404."""
    server, port, callback = gmc_server
    async with aiohttp.ClientSession() as session:
        async with session.get(f"http://127.0.0.1:{port}/other") as resp:
            assert resp.status == 404
