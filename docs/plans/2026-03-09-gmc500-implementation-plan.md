# GQ GMC-500 Home Assistant Integration — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a local-first Home Assistant custom integration that receives radiation data directly from a GQ GMC-500 Geiger counter via WiFi and forwards it to gmcmap.com asynchronously.

**Architecture:** Standalone aiohttp HTTP server within an HA custom component, listening on a configurable port for GET requests from the GMC-500. Parsed data updates HA sensor entities immediately and is forwarded to gmcmap.com in a fire-and-retry background task. Config Flow handles initial setup and device auto-discovery with user confirmation.

**Tech Stack:** Python 3.12+, Home Assistant Core APIs, aiohttp (server + client), voluptuous, pytest + pytest-homeassistant-custom-component

**Design doc:** `docs/plans/2026-03-09-gmc500-ha-integration-design.md`

---

## Task 1: Project Scaffolding & Constants

**Files:**
- Create: `custom_components/gmc500/__init__.py` (stub)
- Create: `custom_components/gmc500/manifest.json`
- Create: `custom_components/gmc500/const.py`
- Create: `custom_components/gmc500/hacs.json`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

**Step 1: Create directory structure**

```bash
mkdir -p custom_components/gmc500/translations
mkdir -p tests
```

**Step 2: Create manifest.json**

```json
{
  "domain": "gmc500",
  "name": "GQ GMC-500 Radiation Monitor",
  "codeowners": [],
  "config_flow": true,
  "dependencies": [],
  "documentation": "https://github.com/TODO",
  "integration_type": "hub",
  "iot_class": "local_push",
  "requirements": [],
  "single_config_entry": true,
  "version": "0.1.0"
}
```

Notes:
- `integration_type: "hub"` because one integration instance manages multiple devices
- `iot_class: "local_push"` because the device pushes data to us locally
- `single_config_entry: true` because only one HTTP server instance is needed
- No extra `requirements` — aiohttp is already part of HA core

**Step 3: Create const.py**

```python
"""Constants for the GQ GMC-500 integration."""

DOMAIN = "gmc500"

DEFAULT_PORT = 8080
GMCMAP_URL = "http://www.gmcmap.com/log2.asp"
GMCMAP_TIMEOUT = 10
GMCMAP_MAX_RETRIES = 3

CONF_PORT = "port"
CONF_IGNORED_DEVICES = "ignored_devices"

# GMC-500 request parameter names
PARAM_AID = "AID"
PARAM_GID = "GID"
PARAM_CPM = "CPM"
PARAM_ACPM = "ACPM"
PARAM_USV = "uSV"
PARAM_TMP = "tmp"
PARAM_HMDT = "hmdt"
PARAM_AP = "ap"

REQUIRED_PARAMS = [PARAM_AID, PARAM_GID, PARAM_CPM, PARAM_ACPM, PARAM_USV]
OPTIONAL_PARAMS = [PARAM_TMP, PARAM_HMDT, PARAM_AP]

# Availability timeout: 3x default logging interval of 5 minutes
AVAILABILITY_TIMEOUT = 900  # 15 minutes in seconds
```

**Step 4: Create stub __init__.py**

```python
"""The GQ GMC-500 Radiation Monitor integration."""
```

**Step 5: Create hacs.json**

```json
{
  "name": "GQ GMC-500 Radiation Monitor",
  "content_in_root": false,
  "render_readme": true,
  "homeassistant": "2024.1.0"
}
```

**Step 6: Create tests/conftest.py**

```python
"""Test fixtures for GMC-500 integration."""

import pytest
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component


@pytest.fixture
def mock_setup_entry():
    """Mock setting up a config entry."""
    with patch(
        "custom_components.gmc500.async_setup_entry",
        return_value=True,
    ) as mock:
        yield mock
```

**Step 7: Create tests/__init__.py**

```python
"""Tests for the GMC-500 integration."""
```

**Step 8: Commit**

```bash
git add custom_components/ tests/ hacs.json
git commit -m "feat: scaffold GMC-500 integration with constants and manifest"
```

---

## Task 2: HTTP Server (server.py)

**Files:**
- Create: `custom_components/gmc500/server.py`
- Create: `tests/test_server.py`

**Step 1: Write failing test — server starts and responds to log2.asp**

```python
"""Tests for the GMC-500 HTTP server."""

import pytest
import aiohttp
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from custom_components.gmc500.server import GMCServer


@pytest.fixture
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
    # No callback should fire for invalid data
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
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server.py -v`
Expected: FAIL — `ImportError: cannot import name 'GMCServer'`

**Step 3: Implement server.py**

```python
"""HTTP server that receives data from GQ GMC-500 Geiger counters."""

from __future__ import annotations

import logging
from typing import Any, Callable, Awaitable

from aiohttp import web

from .const import (
    PARAM_AID,
    PARAM_GID,
    PARAM_CPM,
    PARAM_ACPM,
    PARAM_USV,
    PARAM_TMP,
    PARAM_HMDT,
    PARAM_AP,
    REQUIRED_PARAMS,
    OPTIONAL_PARAMS,
)

_LOGGER = logging.getLogger(__name__)

DataCallback = Callable[[dict[str, Any]], Awaitable[None] | None]


class GMCServer:
    """HTTP server that mimics gmcmap.com/log2.asp endpoint."""

    def __init__(self, port: int, data_callback: DataCallback) -> None:
        """Initialize the server."""
        self._port = port
        self._data_callback = data_callback
        self._app = web.Application()
        self._app.router.add_get("/log2.asp", self._handle_log2)
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None

    async def start(self) -> None:
        """Start the HTTP server."""
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "0.0.0.0", self._port)
        await self._site.start()
        _LOGGER.info("GMC-500 server started on port %s", self._port)

    async def stop(self) -> None:
        """Stop the HTTP server."""
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
        _LOGGER.info("GMC-500 server stopped")

    async def _handle_log2(self, request: web.Request) -> web.Response:
        """Handle incoming log2.asp requests from GMC-500 devices."""
        params = request.query

        # Always respond OK.ERR0 to the device
        response = web.Response(text="OK.ERR0")

        # Validate required parameters
        for param in REQUIRED_PARAMS:
            if param not in params:
                _LOGGER.warning(
                    "Missing required parameter '%s' from %s",
                    param,
                    request.remote,
                )
                return response

        # Parse numeric values
        data: dict[str, Any] = {}
        try:
            data[PARAM_AID] = params[PARAM_AID]
            data[PARAM_GID] = params[PARAM_GID]
            data[PARAM_CPM] = float(params[PARAM_CPM])
            data[PARAM_ACPM] = float(params[PARAM_ACPM])
            data[PARAM_USV] = float(params[PARAM_USV])
        except (ValueError, KeyError) as err:
            _LOGGER.warning("Invalid parameter value: %s", err)
            return response

        # Parse optional parameters
        for param in OPTIONAL_PARAMS:
            if param in params:
                try:
                    data[param] = float(params[param])
                except ValueError:
                    _LOGGER.warning("Invalid optional parameter '%s': %s", param, params[param])

        # Call the data callback
        result = self._data_callback(data)
        if result is not None:
            await result

        return response
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_server.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add custom_components/gmc500/server.py tests/test_server.py
git commit -m "feat: add HTTP server accepting GMC-500 log2.asp requests"
```

---

## Task 3: Coordinator — Data Management & gmcmap.com Forwarding

**Files:**
- Create: `custom_components/gmc500/coordinator.py`
- Create: `tests/test_coordinator.py`

**Step 1: Write failing tests**

```python
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
    # Simulate staleness
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
    # Should have been called 3 times (initial + 2 retries)
    assert mock_session.get.call_count == 3
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_coordinator.py -v`
Expected: FAIL — `ImportError: cannot import name 'GMCCoordinator'`

**Step 3: Implement coordinator.py**

```python
"""Coordinator for GMC-500 data management and gmcmap.com forwarding."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant, callback

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

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize coordinator."""
        self.hass = hass
        self.devices: dict[str, dict[str, Any]] = {}
        self._registered_devices: dict[str, str] = {}  # device_id -> name
        self._ignored_devices: set[str] = set()
        self._listeners: list[callable] = []

    def _device_id(self, aid: str, gid: str) -> str:
        """Create device ID from AID and GID."""
        return f"{aid}_{gid}"

    def register_device(self, aid: str, gid: str, name: str) -> None:
        """Register a device as known."""
        device_id = self._device_id(aid, gid)
        self._registered_devices[device_id] = name

    def is_device_known(self, aid: str, gid: str) -> bool:
        """Check if a device is registered."""
        return self._device_id(aid, gid) in self._registered_devices

    def ignore_device(self, aid: str, gid: str) -> None:
        """Add a device to the ignore list."""
        self._ignored_devices.add(self._device_id(aid, gid))

    def unignore_device(self, aid: str, gid: str) -> None:
        """Remove a device from the ignore list."""
        self._ignored_devices.discard(self._device_id(aid, gid))

    def is_device_ignored(self, aid: str, gid: str) -> bool:
        """Check if a device is ignored."""
        return self._device_id(aid, gid) in self._ignored_devices

    def is_device_available(self, device_id: str) -> bool:
        """Check if a device is available (recently seen)."""
        if device_id not in self.devices:
            return False
        last_seen = self.devices[device_id].get("last_seen")
        if last_seen is None:
            return False
        elapsed = (datetime.now() - last_seen).total_seconds()
        return elapsed <= AVAILABILITY_TIMEOUT

    def add_listener(self, listener: callable) -> callable:
        """Add a listener for data updates. Returns removal callable."""
        self._listeners.append(listener)

        def remove():
            self._listeners.remove(listener)

        return remove

    def process_data(self, data: dict[str, Any]) -> None:
        """Process incoming data from a GMC-500 device."""
        aid = data[PARAM_AID]
        gid = data[PARAM_GID]
        device_id = self._device_id(aid, gid)

        if device_id in self._ignored_devices:
            return

        data["last_seen"] = datetime.now()
        self.devices[device_id] = data

        # Notify listeners
        for listener in self._listeners:
            listener(device_id, data)

        # Forward to gmcmap.com in background
        self.hass.async_create_task(self.forward_to_gmcmap(data))

    async def forward_to_gmcmap(self, data: dict[str, Any]) -> None:
        """Forward measurement data to gmcmap.com with retry."""
        params = {k: v for k, v in data.items() if k != "last_seen"}

        for attempt in range(GMCMAP_MAX_RETRIES):
            try:
                async with aiohttp.ClientSession() as session:
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
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_coordinator.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add custom_components/gmc500/coordinator.py tests/test_coordinator.py
git commit -m "feat: add coordinator for device data management and gmcmap forwarding"
```

---

## Task 4: Sensor Entities

**Files:**
- Create: `custom_components/gmc500/sensor.py`
- Create: `tests/test_sensor.py`

**Step 1: Write failing tests**

```python
"""Tests for GMC-500 sensor entities."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from custom_components.gmc500.sensor import (
    GMCRadiationSensor,
    GMCEnvironmentSensor,
    SENSOR_DESCRIPTIONS,
)
from custom_components.gmc500.const import DOMAIN


@pytest.fixture
def coordinator():
    """Create a mock coordinator."""
    coord = MagicMock()
    coord.devices = {
        "0230111_0034021": {
            "AID": "0230111",
            "GID": "0034021",
            "CPM": 15.0,
            "ACPM": 13.2,
            "uSV": 0.075,
            "last_seen": datetime.now(),
        }
    }
    coord.is_device_available.return_value = True
    return coord


def test_cpm_sensor_value(coordinator):
    """Test CPM sensor returns correct value."""
    sensor = GMCRadiationSensor(
        coordinator, "0230111", "0034021", SENSOR_DESCRIPTIONS["CPM"]
    )
    assert sensor.native_value == 15.0


def test_cpm_sensor_unit(coordinator):
    """Test CPM sensor has correct unit."""
    sensor = GMCRadiationSensor(
        coordinator, "0230111", "0034021", SENSOR_DESCRIPTIONS["CPM"]
    )
    assert sensor.native_unit_of_measurement == "CPM"


def test_usv_sensor_value(coordinator):
    """Test µSv/h sensor returns correct value."""
    sensor = GMCRadiationSensor(
        coordinator, "0230111", "0034021", SENSOR_DESCRIPTIONS["uSV"]
    )
    assert sensor.native_value == 0.075


def test_sensor_unique_id(coordinator):
    """Test sensor unique_id format."""
    sensor = GMCRadiationSensor(
        coordinator, "0230111", "0034021", SENSOR_DESCRIPTIONS["CPM"]
    )
    assert sensor.unique_id == "gmc500_0230111_0034021_cpm"


def test_sensor_device_info(coordinator):
    """Test sensor device info is correct."""
    sensor = GMCRadiationSensor(
        coordinator, "0230111", "0034021", SENSOR_DESCRIPTIONS["CPM"]
    )
    info = sensor.device_info
    assert info["identifiers"] == {(DOMAIN, "0230111_0034021")}
    assert info["manufacturer"] == "GQ Electronics"


def test_sensor_state_class(coordinator):
    """Test all sensors have measurement state class."""
    sensor = GMCRadiationSensor(
        coordinator, "0230111", "0034021", SENSOR_DESCRIPTIONS["CPM"]
    )
    assert sensor.state_class == SensorStateClass.MEASUREMENT


def test_sensor_availability(coordinator):
    """Test sensor availability tracks coordinator."""
    sensor = GMCRadiationSensor(
        coordinator, "0230111", "0034021", SENSOR_DESCRIPTIONS["CPM"]
    )
    assert sensor.available is True
    coordinator.is_device_available.return_value = False
    assert sensor.available is False


def test_temperature_sensor_device_class(coordinator):
    """Test temperature sensor has correct device class."""
    coordinator.devices["0230111_0034021"]["tmp"] = 22.5
    sensor = GMCEnvironmentSensor(
        coordinator, "0230111", "0034021", SENSOR_DESCRIPTIONS["tmp"]
    )
    assert sensor.device_class == SensorDeviceClass.TEMPERATURE
    assert sensor.native_value == 22.5


def test_environment_sensor_none_when_missing(coordinator):
    """Test environment sensor returns None when parameter not in data."""
    sensor = GMCEnvironmentSensor(
        coordinator, "0230111", "0034021", SENSOR_DESCRIPTIONS["tmp"]
    )
    assert sensor.native_value is None
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sensor.py -v`
Expected: FAIL — `ImportError`

**Step 3: Implement sensor.py**

```python
"""Sensor entities for the GQ GMC-500 integration."""

from __future__ import annotations

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


class GMCRadiationSensor(GMCBaseSensor):
    """Sensor for radiation measurements (CPM, ACPM, µSv/h)."""

    @property
    def native_value(self) -> float | None:
        """Return the sensor value."""
        device_data = self._coordinator.devices.get(self._device_id)
        if device_data is None:
            return None
        return device_data.get(self._description.key)


class GMCEnvironmentSensor(GMCBaseSensor):
    """Sensor for environmental measurements (temperature, humidity, pressure)."""

    @property
    def native_value(self) -> float | None:
        """Return the sensor value."""
        device_data = self._coordinator.devices.get(self._device_id)
        if device_data is None:
            return None
        return device_data.get(self._description.key)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GMC-500 sensors from a config entry."""
    coordinator: GMCCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    tracked_devices: set[str] = set()

    @callback
    def _async_handle_data(device_id: str, data: dict[str, Any]) -> None:
        """Handle new data from a device."""
        if device_id in tracked_devices:
            # Already tracking — just trigger state update
            return

        aid = data["AID"]
        gid = data["GID"]

        if not coordinator.is_device_known(aid, gid):
            return

        tracked_devices.add(device_id)
        entities: list[SensorEntity] = []

        # Always add radiation sensors
        for key in RADIATION_SENSORS:
            entities.append(
                GMCRadiationSensor(coordinator, aid, gid, SENSOR_DESCRIPTIONS[key])
            )

        # Add environment sensors if data is present
        for key in ENVIRONMENT_SENSORS:
            if key in data:
                entities.append(
                    GMCEnvironmentSensor(
                        coordinator, aid, gid, SENSOR_DESCRIPTIONS[key]
                    )
                )

        async_add_entities(entities)

    coordinator.add_listener(_async_handle_data)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sensor.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add custom_components/gmc500/sensor.py tests/test_sensor.py
git commit -m "feat: add sensor entities for radiation and environmental data"
```

---

## Task 5: Config Flow — Initial Setup & Options

**Files:**
- Create: `custom_components/gmc500/config_flow.py`
- Create: `custom_components/gmc500/strings.json`
- Create: `custom_components/gmc500/translations/en.json`
- Create: `tests/test_config_flow.py`

**Step 1: Write failing tests**

```python
"""Tests for GMC-500 config flow."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.gmc500.const import DOMAIN, DEFAULT_PORT, CONF_PORT


async def test_user_flow_creates_entry(hass: HomeAssistant):
    """Test user config flow creates a config entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    with patch(
        "custom_components.gmc500.config_flow.test_port_available",
        return_value=True,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PORT: 8080},
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "GQ GMC-500"
    assert result["data"][CONF_PORT] == 8080


async def test_user_flow_port_in_use(hass: HomeAssistant):
    """Test config flow shows error when port is in use."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.gmc500.config_flow.test_port_available",
        return_value=False,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PORT: 8080},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {CONF_PORT: "port_in_use"}


async def test_discovery_flow_confirms_device(hass: HomeAssistant):
    """Test discovery flow lets user confirm a new device."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "discovery"},
        data={
            "aid": "0230111",
            "gid": "0034021",
            "cpm": 15.0,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config_flow.py -v`
Expected: FAIL — `ImportError`

**Step 3: Implement config_flow.py**

```python
"""Config flow for GQ GMC-500 integration."""

from __future__ import annotations

import socket
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback

from .const import DOMAIN, DEFAULT_PORT, CONF_PORT, CONF_IGNORED_DEVICES

_LOGGER = logging.getLogger(__name__)


def test_port_available(port: int) -> bool:
    """Test if a TCP port is available."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        sock.bind(("0.0.0.0", port))
        sock.close()
        return True
    except OSError:
        return False


class GMC500ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for GMC-500."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow."""
        self._discovery_data: dict[str, Any] | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            port = user_input[CONF_PORT]

            available = await self.hass.async_add_executor_job(
                test_port_available, port
            )
            if not available:
                errors[CONF_PORT] = "port_in_use"
            else:
                return self.async_create_entry(
                    title="GQ GMC-500",
                    data={CONF_PORT: port},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
                        int, vol.Range(min=1024, max=65535)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_discovery(
        self, discovery_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle device discovery."""
        self._discovery_data = discovery_data
        aid = discovery_data["aid"]
        gid = discovery_data["gid"]

        await self.async_set_unique_id(f"{aid}_{gid}")
        self._abort_if_unique_id_configured()

        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle user confirmation of discovered device."""
        if user_input is not None:
            return self.async_create_entry(
                title=user_input.get("name", f"GMC-500 {self._discovery_data['gid']}"),
                data=self._discovery_data,
            )

        return self.async_show_form(
            step_id="discovery_confirm",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "name",
                        default=f"GMC-500 {self._discovery_data['gid']}",
                    ): str,
                }
            ),
            description_placeholders={
                "aid": self._discovery_data["aid"],
                "gid": self._discovery_data["gid"],
                "cpm": str(self._discovery_data.get("cpm", "N/A")),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get options flow handler."""
        return GMC500OptionsFlow(config_entry)


class GMC500OptionsFlow(OptionsFlow):
    """Handle options flow for GMC-500."""

    def __init__(self, config_entry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            port = user_input[CONF_PORT]
            current_port = self.config_entry.data.get(CONF_PORT, DEFAULT_PORT)

            if port != current_port:
                available = await self.hass.async_add_executor_job(
                    test_port_available, port
                )
                if not available:
                    errors[CONF_PORT] = "port_in_use"

            if not errors:
                return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_PORT,
                        default=self.config_entry.options.get(
                            CONF_PORT,
                            self.config_entry.data.get(CONF_PORT, DEFAULT_PORT),
                        ),
                    ): vol.All(int, vol.Range(min=1024, max=65535)),
                }
            ),
            errors=errors,
        )
```

**Step 4: Create strings.json**

```json
{
  "config": {
    "step": {
      "user": {
        "title": "GQ GMC-500 Radiation Monitor",
        "description": "Configure the HTTP server that receives data from your GMC-500 Geiger counter.",
        "data": {
          "port": "HTTP Server Port"
        },
        "data_description": {
          "port": "Port for receiving GMC-500 data (1024-65535)"
        }
      },
      "discovery_confirm": {
        "title": "New Geiger Counter Detected",
        "description": "A new GMC-500 device was detected.\n\nAccount ID: {aid}\nDevice ID: {gid}\nLast CPM: {cpm}",
        "data": {
          "name": "Device Name"
        }
      }
    },
    "error": {
      "port_in_use": "Port is already in use"
    },
    "abort": {
      "already_configured": "This device is already configured"
    }
  },
  "options": {
    "step": {
      "init": {
        "title": "GQ GMC-500 Options",
        "data": {
          "port": "HTTP Server Port"
        }
      }
    },
    "error": {
      "port_in_use": "Port is already in use"
    }
  }
}
```

**Step 5: Copy strings.json to translations/en.json**

```bash
cp custom_components/gmc500/strings.json custom_components/gmc500/translations/en.json
```

**Step 6: Run tests to verify they pass**

Run: `pytest tests/test_config_flow.py -v`
Expected: All tests PASS

**Step 7: Commit**

```bash
git add custom_components/gmc500/config_flow.py custom_components/gmc500/strings.json custom_components/gmc500/translations/ tests/test_config_flow.py
git commit -m "feat: add config flow with device discovery and options"
```

---

## Task 6: Integration Setup (__init__.py)

**Files:**
- Modify: `custom_components/gmc500/__init__.py`
- Create: `tests/test_init.py`

**Step 1: Write failing tests**

```python
"""Tests for GMC-500 integration setup."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntryState

from custom_components.gmc500.const import DOMAIN, CONF_PORT


@pytest.fixture
def config_entry(hass):
    """Create a mock config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {CONF_PORT: 18080}
    entry.options = {}
    entry.async_on_unload = MagicMock()
    return entry


@pytest.mark.asyncio
async def test_setup_entry_starts_server(hass: HomeAssistant, config_entry):
    """Test that setup starts the HTTP server."""
    with patch(
        "custom_components.gmc500.GMCServer", autospec=True
    ) as mock_server_cls, patch(
        "custom_components.gmc500.async_forward_entry_setups",
        new_callable=AsyncMock,
    ):
        mock_server = mock_server_cls.return_value
        mock_server.start = AsyncMock()

        from custom_components.gmc500 import async_setup_entry

        result = await async_setup_entry(hass, config_entry)
        assert result is True
        mock_server.start.assert_called_once()


@pytest.mark.asyncio
async def test_unload_entry_stops_server(hass: HomeAssistant, config_entry):
    """Test that unload stops the HTTP server."""
    with patch(
        "custom_components.gmc500.GMCServer", autospec=True
    ) as mock_server_cls, patch(
        "custom_components.gmc500.async_forward_entry_setups",
        new_callable=AsyncMock,
    ):
        mock_server = mock_server_cls.return_value
        mock_server.start = AsyncMock()
        mock_server.stop = AsyncMock()

        from custom_components.gmc500 import async_setup_entry, async_unload_entry

        hass.data.setdefault(DOMAIN, {})
        await async_setup_entry(hass, config_entry)

        with patch(
            "custom_components.gmc500.async_unload_platforms",
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await async_unload_entry(hass, config_entry)
            assert result is True
            mock_server.stop.assert_called_once()
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_init.py -v`
Expected: FAIL

**Step 3: Implement __init__.py**

```python
"""The GQ GMC-500 Radiation Monitor integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_PORT, DEFAULT_PORT
from .coordinator import GMCCoordinator
from .server import GMCServer

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up GMC-500 from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = GMCCoordinator(hass)
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)

    async def handle_data(data: dict[str, Any]) -> None:
        """Handle incoming data from a GMC-500 device."""
        aid = data["AID"]
        gid = data["GID"]

        if coordinator.is_device_ignored(aid, gid):
            return

        if not coordinator.is_device_known(aid, gid):
            # Trigger discovery flow
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
            # Store data temporarily so it's not lost
            coordinator.process_data(data)
            return

        coordinator.process_data(data)

    server = GMCServer(port=port, data_callback=handle_data)
    await server.start()

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "server": server,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(
        entry.add_update_listener(_async_update_listener)
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["server"].stop()

    return unload_ok


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Handle options update — restart integration."""
    await hass.config_entries.async_reload(entry.entry_id)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_init.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add custom_components/gmc500/__init__.py tests/test_init.py
git commit -m "feat: add integration setup with server lifecycle management"
```

---

## Task 7: Integration Test — Full Data Flow

**Files:**
- Create: `tests/test_integration.py`

**Step 1: Write integration test**

```python
"""Integration tests for the full GMC-500 data flow."""

import pytest
import aiohttp
from unittest.mock import patch, AsyncMock

from custom_components.gmc500.server import GMCServer
from custom_components.gmc500.coordinator import GMCCoordinator


@pytest.mark.asyncio
async def test_full_flow_server_to_coordinator(unused_tcp_port):
    """Test complete data flow: HTTP request → coordinator → gmcmap forwarding."""
    from unittest.mock import MagicMock

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
```

**Step 2: Run integration test**

Run: `pytest tests/test_integration.py -v`
Expected: PASS

**Step 3: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add integration test for full data flow"
```

---

## Task 8: HACS & Repository Finalization

**Files:**
- Verify: `hacs.json` (created in Task 1)
- Create: `README.md`

**Step 1: Create README.md**

```markdown
# GQ GMC-500 Home Assistant Integration

Custom Home Assistant integration that receives radiation measurement data directly
from a GQ Electronics GMC-500 Geiger counter via WiFi, without depending on gmcmap.com.

## Features

- **Local-first**: Data is received directly from the GMC-500, no cloud dependency
- **gmcmap.com forwarding**: Data is forwarded to gmcmap.com asynchronously with retry
- **Auto-discovery**: New devices are detected automatically and presented for confirmation
- **Multiple devices**: One integration instance supports multiple GMC-500 counters

## Sensors

- CPM (Counts Per Minute)
- ACPM (Average CPM)
- µSv/h (Dose Rate)
- Temperature (if available)
- Humidity (if available)
- Atmospheric Pressure (if available)

## Installation

### HACS (recommended)

1. Add this repository as a custom repository in HACS
2. Install "GQ GMC-500 Radiation Monitor"
3. Restart Home Assistant
4. Go to Settings → Integrations → Add Integration → "GQ GMC-500"

### Manual

1. Copy `custom_components/gmc500/` to your HA `config/custom_components/` directory
2. Restart Home Assistant
3. Go to Settings → Integrations → Add Integration → "GQ GMC-500"

## GMC-500 Configuration

On your GMC-500 Geiger counter, set:
- **Website Server**: `<your-ha-ip>:<port>` (e.g., `192.168.1.100:8080`)
- **URL**: `log2.asp`
- **User ID**: Your gmcmap.com Account ID
- **Counter ID**: Your gmcmap.com Geiger Counter ID
```

**Step 2: Run all tests one final time**

Run: `pytest tests/ -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add README with installation and configuration instructions"
```

---

## Summary

| Task | Beschreibung | Dateien |
|------|-------------|---------|
| 1 | Scaffolding & Constants | manifest.json, const.py, hacs.json, conftest.py |
| 2 | HTTP Server | server.py, test_server.py |
| 3 | Coordinator & Forwarding | coordinator.py, test_coordinator.py |
| 4 | Sensor Entities | sensor.py, test_sensor.py |
| 5 | Config Flow | config_flow.py, strings.json, translations/, test_config_flow.py |
| 6 | Integration Setup | __init__.py, test_init.py |
| 7 | Integration Test | test_integration.py |
| 8 | HACS & README | README.md |
