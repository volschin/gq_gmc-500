# HA Gold Quality Scale Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Bring the gmc500 custom integration from v0.1.0 to HA Quality Scale Gold standard by satisfying all Bronze, Silver, and Gold rules.

**Architecture:** Incremental improvements across all modules in dependency order. Each task is independently testable. Tests run with `.venv/bin/pytest tests/ -v`. HA is NOT installed — all HA modules are mocked in `tests/conftest.py` and per-file mock blocks.

**Tech Stack:** Python 3.13, aiohttp, pytest, pytest-asyncio (asyncio_mode=auto), homeassistant mocked via sys.modules

---

## Quality Scale Gap Summary

| Rule | Tier | Status |
|------|------|--------|
| runtime-data (typed ConfigEntry) | Bronze | ✗ |
| test-before-setup (ConfigEntryNotReady) | Bronze | ✗ |
| entity-event-setup (async_added_to_hass) | Bronze | ✗ |
| has-entity-name | Bronze | ✓ |
| entity-unique-id | Bronze | ✓ |
| config-flow + config-flow-test-coverage | Bronze | ✓ |
| unique-config-entry | Bronze | ✓ |
| integration-owner (CODEOWNERS) | Silver | ✗ |
| parallel-updates | Silver | ✗ |
| log-when-unavailable | Silver | ✗ |
| config-entry-unloading | Silver | ✓ |
| entity-unavailable | Silver | ✓ |
| reauthentication-flow | Silver | N/A (no auth) |
| test-coverage >95% | Silver | ✗ |
| diagnostics | Gold | ✗ |
| stale-devices | Gold | ✗ |
| reconfiguration-flow | Gold | ✗ |
| entity-translations | Gold | ✗ |
| icon-translations | Gold | ✗ |
| entity-category | Gold | ✗ |
| entity-disabled-by-default | Gold | ✗ |
| exception-translations | Gold | ✗ |
| repair-issues | Gold | ✗ |
| devices (DeviceInfo) | Gold | ✓ |
| dynamic-devices | Gold | ✓ |
| discovery | Gold | ✓ (custom push) |
| discovery-update-info | Gold | N/A (no IP stored) |
| docs-* (7 sections) | Gold | ✗ |

---

## Task 1: Typed runtime-data (Bronze)

Replace `hass.data[DOMAIN][entry.entry_id]` with `entry.runtime_data` using a typed `GMCConfigEntry` alias.

**Files:**
- Modify: `custom_components/gmc500/__init__.py`
- Modify: `custom_components/gmc500/sensor.py`
- Modify: `tests/test_init.py`
- Modify: `tests/test_sensor.py`

**Step 1: Write the failing tests**

In `tests/test_init.py`, replace the `_make_entry` helper and update the two assertions that check `hass.data`:

```python
def _make_entry(entry_id="test_entry_id", port=8080):
    """Create a mock ConfigEntry."""
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.data = {"port": port}
    entry.async_on_unload = MagicMock()
    entry.add_update_listener = MagicMock()
    entry.runtime_data = None  # Will be set by async_setup_entry
    return entry
```

Update `test_starts_server_and_stores_data` to check `entry.runtime_data` instead of `hass.data`:

```python
async def test_starts_server_and_stores_data(self):
    hass = _make_hass()
    entry = _make_entry()

    with patch("custom_components.gmc500.GMCServer") as mock_server_cls, \
         patch("custom_components.gmc500.GMCCoordinator") as mock_coord_cls:
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
```

Update `test_stops_server_and_removes_data` to set runtime_data on entry:

```python
async def test_stops_server_and_removes_data(self):
    hass = _make_hass()
    entry = _make_entry()
    mock_server = AsyncMock()
    entry.runtime_data = MagicMock()
    entry.runtime_data.server = mock_server

    result = await async_unload_entry(hass, entry)

    assert result is True
    mock_server.stop.assert_awaited_once()
```

Update `test_does_not_remove_data_on_failed_unload`:

```python
async def test_does_not_remove_data_on_failed_unload(self):
    hass = _make_hass()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)
    entry = _make_entry()
    mock_server = AsyncMock()
    entry.runtime_data = MagicMock()
    entry.runtime_data.server = mock_server

    result = await async_unload_entry(hass, entry)

    assert result is False
    mock_server.stop.assert_not_awaited()
```

Remove `hass.data = {...}` setup from `TestHandleDataCallback` tests (the callback no longer uses hass.data).

In `tests/test_sensor.py`, update `TestAsyncSetupEntry` to set `entry.runtime_data` instead of `hass.data`:

```python
async def test_listener_creates_radiation_sensors_for_known_device(self):
    hass = MagicMock()
    coordinator = GMCCoordinator(hass)
    coordinator.register_device(AID, GID, "My Counter")

    entry = MagicMock()
    entry.runtime_data = MagicMock()
    entry.runtime_data.coordinator = coordinator

    added_entities: list = []
    async_add_entities = MagicMock(side_effect=lambda e: added_entities.extend(e))

    await async_setup_entry(hass, entry, async_add_entities)
    coordinator.process_data(_valid_data())

    assert len(added_entities) == len(RADIATION_SENSORS)
```

Apply same `entry.runtime_data.coordinator = coordinator` pattern to the other 3 `TestAsyncSetupEntry` tests.

**Step 2: Run tests to see them fail**

```bash
.venv/bin/pytest tests/test_init.py tests/test_sensor.py -v
```

Expected: failures referencing `hass.data` key errors and `runtime_data` attribute.

**Step 3: Add `GMCRuntimeData` dataclass and typed alias to `__init__.py`**

```python
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
                    data={"aid": aid, "gid": gid, "cpm": data.get("CPM")},
                )
            )
            coordinator.process_data(data)
            return

        coordinator.process_data(data)

    server = GMCServer(port=port, data_callback=handle_data)
    await server.start()

    entry.runtime_data = GMCRuntimeData(coordinator=coordinator, server=server)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

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
```

**Step 4: Update `sensor.py` to use `entry.runtime_data`**

Replace:
```python
coordinator: GMCCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
```
With:
```python
coordinator: GMCCoordinator = entry.runtime_data.coordinator
```

Remove the import of `DOMAIN` from sensor.py if it's only used for hass.data access (keep it for other uses like `unique_id`).

**Step 5: Run tests to confirm green**

```bash
.venv/bin/pytest tests/test_init.py tests/test_sensor.py -v
```

Expected: all pass.

**Step 6: Run full suite**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all pass.

**Step 7: Commit**

```bash
git add custom_components/gmc500/__init__.py custom_components/gmc500/sensor.py tests/test_init.py tests/test_sensor.py
git commit -m "refactor: use typed ConfigEntry runtime_data instead of hass.data"
```

---

## Task 2: CODEOWNERS and manifest.json (Silver: integration-owner)

No tests needed for these files.

**Step 1: Create `CODEOWNERS` at repo root**

```
# Home Assistant Integration Owners
custom_components/gmc500/ @volschin
```

**Step 2: Update `custom_components/gmc500/manifest.json`**

```json
{
  "domain": "gmc500",
  "name": "GQ GMC-500 Radiation Monitor",
  "codeowners": ["@volschin"],
  "config_flow": true,
  "dependencies": [],
  "documentation": "https://github.com/volschin/gq_gmc-500",
  "integration_type": "hub",
  "iot_class": "local_push",
  "quality_scale": "gold",
  "requirements": [],
  "single_config_entry": true,
  "version": "0.1.0"
}
```

**Step 3: Run full suite to verify nothing broke**

```bash
.venv/bin/pytest tests/ -v
```

**Step 4: Commit**

```bash
git add CODEOWNERS custom_components/gmc500/manifest.json
git commit -m "chore: add CODEOWNERS and fix manifest.json (quality_scale, docs URL)"
```

---

## Task 3: PARALLEL_UPDATES (Silver)

**Files:**
- Modify: `custom_components/gmc500/sensor.py`

**Step 1: Add `PARALLEL_UPDATES = 0` to `sensor.py`**

Add after the imports, before `SENSOR_DESCRIPTIONS`:

```python
# Push-based integration — coordinator handles updates, no parallel polling needed
PARALLEL_UPDATES = 0
```

**Step 2: Run tests**

```bash
.venv/bin/pytest tests/test_sensor.py -v
```

Expected: all pass (this is a module-level constant, no behavior change).

**Step 3: Commit**

```bash
git add custom_components/gmc500/sensor.py
git commit -m "feat: add PARALLEL_UPDATES=0 for push-based sensor platform"
```

---

## Task 4: test-before-setup + repair-issues + exception-translations (Bronze + Gold)

Raise `ConfigEntryNotReady` (with translation) when the HTTP server cannot bind. Create a repair issue so the user sees an actionable fix in the UI.

**Files:**
- Modify: `custom_components/gmc500/__init__.py`
- Modify: `custom_components/gmc500/strings.json`
- Modify: `custom_components/gmc500/translations/en.json`
- Modify: `tests/test_init.py`
- Modify: `tests/conftest.py`

**Step 1: Add mock for `homeassistant.exceptions` and `homeassistant.helpers.issue_registry` to `tests/conftest.py`**

Add to the `sys.modules.setdefault(...)` block:

```python
_ha_exceptions = MagicMock()

class _ConfigEntryNotReady(Exception):
    def __init__(self, *args, translation_domain=None, translation_key=None,
                 translation_placeholders=None, **kwargs):
        super().__init__(*args)
        self.translation_domain = translation_domain
        self.translation_key = translation_key
        self.translation_placeholders = translation_placeholders

_ha_exceptions.ConfigEntryNotReady = _ConfigEntryNotReady

_ha_issue_registry = MagicMock()
_ha_issue_registry.IssueSeverity = MagicMock()
_ha_issue_registry.IssueSeverity.ERROR = "error"

sys.modules.setdefault("homeassistant.exceptions", _ha_exceptions)
sys.modules.setdefault("homeassistant.helpers.issue_registry", _ha_issue_registry)
```

Also add the same mocks to `test_init.py`'s local `sys.modules.setdefault` block (before the imports).

**Step 2: Write the failing test in `tests/test_init.py`**

Add a new class:

```python
from custom_components.gmc500 import async_setup_entry  # already imported


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

        hass = _make_hass()
        entry = _make_entry()

        with patch("custom_components.gmc500.GMCServer") as mock_server_cls, \
             patch("custom_components.gmc500.GMCCoordinator"):
            mock_server_cls.return_value = AsyncMock()
            await async_setup_entry(hass, entry)

        ir.async_delete_issue.assert_called_once()
```

**Step 3: Run to confirm failures**

```bash
.venv/bin/pytest tests/test_init.py::TestSetupFailure -v
```

Expected: 3 failures (ConfigEntryNotReady not raised, ir not called).

**Step 4: Update `__init__.py` to handle OSError**

Add imports at top:
```python
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import issue_registry as ir
```

In `async_setup_entry`, replace `await server.start()` with:

```python
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
```

**Step 5: Add translation strings**

In `strings.json`, add a top-level `"issues"` section and an `"exceptions"` section:

```json
{
  "config": { ... },
  "options": { ... },
  "issues": {
    "port_in_use": {
      "title": "Port {port} is in use",
      "description": "The HTTP port {port} configured for GMC-500 is already in use. Change the port in the integration options."
    }
  },
  "exceptions": {
    "port_unavailable": {
      "message": "Cannot start HTTP server on port {port}: port is already in use."
    }
  }
}
```

Copy the same additions to `translations/en.json`.

**Step 6: Run tests to confirm green**

```bash
.venv/bin/pytest tests/test_init.py -v
```

Expected: all pass.

**Step 7: Commit**

```bash
git add custom_components/gmc500/__init__.py custom_components/gmc500/strings.json custom_components/gmc500/translations/en.json tests/test_init.py tests/conftest.py
git commit -m "feat: raise ConfigEntryNotReady and repair issue when port unavailable"
```

---

## Task 5: entity-event-setup — async_added_to_hass (Bronze)

Sensor entities must subscribe to coordinator updates in `async_added_to_hass` and unsubscribe in `async_will_remove_from_hass`. This also enables proper push updates (entities call `async_write_ha_state()` on new data).

**Files:**
- Modify: `custom_components/gmc500/sensor.py`
- Modify: `tests/test_sensor.py`
- Modify: `tests/conftest.py`

**Step 1: Add `async_write_ha_state` to the mock `SensorEntity` base in `conftest.py`**

```python
_ha_sensor.SensorEntity = type(
    "SensorEntity",
    (),
    {
        "async_write_ha_state": MagicMock(),
        "async_added_to_hass": AsyncMock(),
        "async_will_remove_from_hass": AsyncMock(),
    },
)
```

Also do the same in `test_sensor.py`'s local mock block (same pattern).

**Step 2: Write failing tests in `tests/test_sensor.py`**

Add a new test class:

```python
class TestEntityLifecycle:
    """Tests for async_added_to_hass and async_will_remove_from_hass."""

    @pytest.mark.asyncio
    async def test_async_added_to_hass_registers_listener(self):
        """async_added_to_hass registers a coordinator listener."""
        coordinator = _make_coordinator()
        sensor = GMCRadiationSensor(
            coordinator, AID, GID, SENSOR_DESCRIPTIONS["CPM"]
        )
        initial_count = len(coordinator._listeners)

        await sensor.async_added_to_hass()

        assert len(coordinator._listeners) == initial_count + 1

    @pytest.mark.asyncio
    async def test_async_will_remove_from_hass_removes_listener(self):
        """async_will_remove_from_hass unregisters the coordinator listener."""
        coordinator = _make_coordinator()
        sensor = GMCRadiationSensor(
            coordinator, AID, GID, SENSOR_DESCRIPTIONS["CPM"]
        )
        await sensor.async_added_to_hass()
        count_after_add = len(coordinator._listeners)

        await sensor.async_will_remove_from_hass()

        assert len(coordinator._listeners) == count_after_add - 1

    def test_coordinator_update_calls_write_ha_state(self):
        """Coordinator data triggers async_write_ha_state on the matching sensor."""
        coordinator = _make_coordinator()
        sensor = GMCRadiationSensor(
            coordinator, AID, GID, SENSOR_DESCRIPTIONS["CPM"]
        )
        sensor.async_write_ha_state = MagicMock()

        # Simulate what async_added_to_hass does: register listener
        coordinator.add_listener(sensor._handle_coordinator_update)

        coordinator.process_data(_valid_data())

        sensor.async_write_ha_state.assert_called_once()

    def test_coordinator_update_ignores_other_device(self):
        """Coordinator data for a different device does NOT trigger write_ha_state."""
        coordinator = _make_coordinator()
        sensor = GMCRadiationSensor(
            coordinator, AID, GID, SENSOR_DESCRIPTIONS["CPM"]
        )
        sensor.async_write_ha_state = MagicMock()

        coordinator.add_listener(sensor._handle_coordinator_update)

        other_data = {
            "AID": "9999999", "GID": "8888888", "CPM": 99.0,
            "ACPM": 99.0, "uSV": 0.5,
        }
        coordinator.process_data(other_data)

        sensor.async_write_ha_state.assert_not_called()
```

**Step 3: Run to confirm failures**

```bash
.venv/bin/pytest tests/test_sensor.py::TestEntityLifecycle -v
```

Expected: AttributeError on `async_added_to_hass` / `_handle_coordinator_update`.

**Step 4: Implement in `sensor.py`**

Add `Callable` to imports:
```python
from collections.abc import Callable
```

Update `GMCBaseSensor`:

```python
class GMCBaseSensor(SensorEntity):
    """Base class for GMC-500 sensors."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_has_entity_name = True
    _remove_listener: Callable[[], None] | None = None

    def __init__(self, ...) -> None:
        # existing code unchanged

    async def async_added_to_hass(self) -> None:
        """Register coordinator listener when added to Home Assistant."""
        self._remove_listener = self._coordinator.add_listener(
            self._handle_coordinator_update
        )

    async def async_will_remove_from_hass(self) -> None:
        """Unregister coordinator listener when removed from Home Assistant."""
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None

    @callback
    def _handle_coordinator_update(self, device_id: str, data: dict) -> None:
        """Write HA state when coordinator has new data for this device."""
        if device_id == self._device_id:
            self.async_write_ha_state()

    # ... rest of existing methods unchanged
```

**Step 5: Run tests to confirm green**

```bash
.venv/bin/pytest tests/test_sensor.py -v
```

Expected: all pass.

**Step 6: Commit**

```bash
git add custom_components/gmc500/sensor.py tests/test_sensor.py tests/conftest.py
git commit -m "feat: subscribe to coordinator updates in async_added_to_hass"
```

---

## Task 6: entity-translations + icon-translations (Gold)

CPM, ACPM, and Dose Rate sensors lack a standard HA device class, so they need `_attr_translation_key` and entries in `strings.json`. Icons move to `icons.json`.

**Files:**
- Modify: `custom_components/gmc500/sensor.py`
- Create: `custom_components/gmc500/icons.json`
- Modify: `custom_components/gmc500/strings.json`
- Modify: `custom_components/gmc500/translations/en.json`
- Modify: `tests/test_sensor.py`

**Step 1: Update existing tests that rely on `_attr_name` and `_attr_icon`**

In `tests/test_sensor.py`, change `test_sensor_name`:

```python
def test_sensor_translation_key_cpm(self):
    """CPM sensor has translation key set."""
    coordinator = _make_coordinator()
    sensor = GMCRadiationSensor(
        coordinator, AID, GID, SENSOR_DESCRIPTIONS["CPM"]
    )
    assert sensor._attr_translation_key == "cpm"

def test_sensor_translation_key_acpm(self):
    """ACPM sensor has translation key set."""
    coordinator = _make_coordinator()
    sensor = GMCRadiationSensor(
        coordinator, AID, GID, SENSOR_DESCRIPTIONS["ACPM"]
    )
    assert sensor._attr_translation_key == "acpm"

def test_sensor_translation_key_dose_rate(self):
    """Dose rate sensor has translation key set."""
    coordinator = _make_coordinator()
    sensor = GMCRadiationSensor(
        coordinator, AID, GID, SENSOR_DESCRIPTIONS["uSV"]
    )
    assert sensor._attr_translation_key == "dose_rate"

def test_sensor_no_hardcoded_icon_for_radiation(self):
    """Radiation sensors do not have a hardcoded icon (uses icons.json)."""
    coordinator = _make_coordinator()
    sensor = GMCRadiationSensor(
        coordinator, AID, GID, SENSOR_DESCRIPTIONS["CPM"]
    )
    assert sensor._attr_icon is None
```

Remove `test_sensor_name` (replaced by translation key tests) and `test_sensor_icon` (replaced by `test_sensor_no_hardcoded_icon_for_radiation`).

**Step 2: Run failing tests**

```bash
.venv/bin/pytest tests/test_sensor.py::TestSensorAttributes -v
```

Expected: failures on translation_key and icon.

**Step 3: Update `GMCSensorDescription` dataclass in `sensor.py`**

Replace the `name: str` and `icon: str | None` fields with:

```python
@dataclass
class GMCSensorDescription:
    """Describe a GMC-500 sensor."""

    key: str
    unit: str
    translation_key: str | None = None
    device_class: SensorDeviceClass | None = None
```

Update `SENSOR_DESCRIPTIONS`:

```python
SENSOR_DESCRIPTIONS: dict[str, GMCSensorDescription] = {
    "CPM": GMCSensorDescription(
        key="CPM", unit="CPM", translation_key="cpm"
    ),
    "ACPM": GMCSensorDescription(
        key="ACPM", unit="CPM", translation_key="acpm"
    ),
    "uSV": GMCSensorDescription(
        key="uSV", unit="µSv/h", translation_key="dose_rate"
    ),
    "tmp": GMCSensorDescription(
        key="tmp",
        unit="°C",
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    "hmdt": GMCSensorDescription(
        key="hmdt",
        unit="%",
        device_class=SensorDeviceClass.HUMIDITY,
    ),
    "ap": GMCSensorDescription(
        key="ap",
        unit="hPa",
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
    ),
}
```

In `GMCBaseSensor.__init__`, replace name/icon lines with:

```python
        self._attr_unique_id = f"{DOMAIN}_{aid}_{gid}_{description.key.lower()}"
        self._attr_native_unit_of_measurement = description.unit
        self._attr_device_class = description.device_class
        self._attr_translation_key = description.translation_key
        # Name is provided by translation_key lookup (radiation) or device class (env)
```

Remove `self._attr_name = description.name` and `self._attr_icon = description.icon`.

**Step 4: Create `custom_components/gmc500/icons.json`**

```json
{
  "entity": {
    "sensor": {
      "cpm": {
        "default": "mdi:radioactive"
      },
      "acpm": {
        "default": "mdi:radioactive"
      },
      "dose_rate": {
        "default": "mdi:radioactive"
      }
    }
  }
}
```

**Step 5: Update `strings.json` — add `entity` section**

Add alongside the existing `config` / `options` keys:

```json
  "entity": {
    "sensor": {
      "cpm": {
        "name": "CPM"
      },
      "acpm": {
        "name": "Average CPM"
      },
      "dose_rate": {
        "name": "Dose Rate"
      }
    }
  }
```

Copy the same `entity` block to `translations/en.json`.

**Step 6: Run tests to confirm green**

```bash
.venv/bin/pytest tests/test_sensor.py -v
```

Expected: all pass.

**Step 7: Commit**

```bash
git add custom_components/gmc500/sensor.py custom_components/gmc500/icons.json custom_components/gmc500/strings.json custom_components/gmc500/translations/en.json tests/test_sensor.py
git commit -m "feat: add entity translation keys and icon-translations via icons.json"
```

---

## Task 7: entity-category + entity-disabled-by-default (Gold)

ACPM is a secondary/diagnostic measurement, less commonly used than CPM. Mark it as `EntityCategory.DIAGNOSTIC` and disabled by default.

**Files:**
- Modify: `custom_components/gmc500/sensor.py`
- Modify: `tests/test_sensor.py`
- Modify: `tests/conftest.py`

**Step 1: Add `EntityCategory` mock to `conftest.py`**

```python
_ha_entity.EntityCategory = MagicMock()
_ha_entity.EntityCategory.DIAGNOSTIC = "diagnostic"
```

Also add to `test_sensor.py`'s local entity mock block.

Add `homeassistant.helpers.entity` import in conftest module list if not already exposing EntityCategory (it should be since `_ha_entity = MagicMock()` with explicit `EntityCategory` set above).

**Step 2: Write failing tests in `tests/test_sensor.py`**

```python
class TestEntityCategoryAndDefault:
    """Tests for entity category and registry default."""

    def test_acpm_is_diagnostic(self):
        """ACPM sensor has EntityCategory.DIAGNOSTIC."""
        coordinator = _make_coordinator()
        sensor = GMCRadiationSensor(
            coordinator, AID, GID, SENSOR_DESCRIPTIONS["ACPM"]
        )
        assert sensor._attr_entity_category == "diagnostic"

    def test_acpm_is_disabled_by_default(self):
        """ACPM sensor is disabled in the entity registry by default."""
        coordinator = _make_coordinator()
        sensor = GMCRadiationSensor(
            coordinator, AID, GID, SENSOR_DESCRIPTIONS["ACPM"]
        )
        assert sensor._attr_entity_registry_enabled_default is False

    def test_cpm_is_not_diagnostic(self):
        """CPM sensor has no entity category (primary sensor)."""
        coordinator = _make_coordinator()
        sensor = GMCRadiationSensor(
            coordinator, AID, GID, SENSOR_DESCRIPTIONS["CPM"]
        )
        assert sensor._attr_entity_category is None

    def test_cpm_is_enabled_by_default(self):
        """CPM sensor is enabled by default."""
        coordinator = _make_coordinator()
        sensor = GMCRadiationSensor(
            coordinator, AID, GID, SENSOR_DESCRIPTIONS["CPM"]
        )
        assert sensor._attr_entity_registry_enabled_default is True
```

**Step 3: Run to confirm failures**

```bash
.venv/bin/pytest tests/test_sensor.py::TestEntityCategoryAndDefault -v
```

**Step 4: Update `GMCSensorDescription` and `GMCBaseSensor` in `sensor.py`**

Add to dataclass:
```python
from homeassistant.helpers.entity import EntityCategory

@dataclass
class GMCSensorDescription:
    key: str
    unit: str
    translation_key: str | None = None
    device_class: SensorDeviceClass | None = None
    entity_category: EntityCategory | None = None
    entity_registry_enabled_default: bool = True
```

Update ACPM description:
```python
    "ACPM": GMCSensorDescription(
        key="ACPM",
        unit="CPM",
        translation_key="acpm",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
```

In `GMCBaseSensor.__init__`, add:
```python
        self._attr_entity_category = description.entity_category
        self._attr_entity_registry_enabled_default = description.entity_registry_enabled_default
```

**Step 5: Run tests to confirm green**

```bash
.venv/bin/pytest tests/test_sensor.py -v
```

**Step 6: Commit**

```bash
git add custom_components/gmc500/sensor.py tests/test_sensor.py tests/conftest.py
git commit -m "feat: mark ACPM as diagnostic and disabled by default"
```

---

## Task 8: reconfiguration-flow (Gold)

Allow users to change the port without removing and re-adding the integration.

**Files:**
- Modify: `custom_components/gmc500/config_flow.py`
- Modify: `custom_components/gmc500/strings.json`
- Modify: `custom_components/gmc500/translations/en.json`
- Modify: `tests/test_config_flow.py`

**Step 1: Write failing tests in `tests/test_config_flow.py`**

```python
class TestReconfigureFlow:
    """Tests for async_step_reconfigure."""

    @pytest.mark.asyncio
    async def test_reconfigure_shows_form(self):
        """Reconfigure step shows a form with current port pre-filled."""
        flow = GMC500ConfigFlow()
        flow.hass = MagicMock()
        entry = MagicMock()
        entry.data = {CONF_PORT: 8080}
        flow._get_reconfigure_entry = MagicMock(return_value=entry)

        result = await flow.async_step_reconfigure(None)

        assert result["type"] == "form"
        assert result["step_id"] == "reconfigure"

    @pytest.mark.asyncio
    async def test_reconfigure_updates_port(self):
        """Reconfigure with valid port updates the entry and reloads."""
        flow = GMC500ConfigFlow()
        flow.hass = MagicMock()
        flow.hass.async_add_executor_job = AsyncMock(return_value=True)
        entry = MagicMock()
        entry.data = {CONF_PORT: 8080}
        flow._get_reconfigure_entry = MagicMock(return_value=entry)
        flow.async_update_reload_and_abort = MagicMock(
            return_value={"type": "abort", "reason": "reconfigure_successful"}
        )

        result = await flow.async_step_reconfigure({CONF_PORT: 9090})

        flow.async_update_reload_and_abort.assert_called_once()

    @pytest.mark.asyncio
    async def test_reconfigure_rejects_port_in_use(self):
        """Reconfigure shows error when new port is already in use."""
        flow = GMC500ConfigFlow()
        flow.hass = MagicMock()
        flow.hass.async_add_executor_job = AsyncMock(return_value=False)
        entry = MagicMock()
        entry.data = {CONF_PORT: 8080}
        flow._get_reconfigure_entry = MagicMock(return_value=entry)

        result = await flow.async_step_reconfigure({CONF_PORT: 9999})

        assert result["type"] == "form"
        assert result["errors"][CONF_PORT] == "port_in_use"
```

**Step 2: Run to confirm failures**

```bash
.venv/bin/pytest tests/test_config_flow.py::TestReconfigureFlow -v
```

**Step 3: Add `async_step_reconfigure` to `GMC500ConfigFlow` in `config_flow.py`**

```python
    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of the integration."""
        errors: dict[str, str] = {}
        reconfigure_entry = self._get_reconfigure_entry()

        if user_input is not None:
            port = user_input[CONF_PORT]
            available = await self.hass.async_add_executor_job(
                test_port_available, port
            )
            if not available:
                errors[CONF_PORT] = "port_in_use"
            else:
                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    data_updates={CONF_PORT: port},
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_PORT,
                        default=reconfigure_entry.data.get(CONF_PORT, DEFAULT_PORT),
                    ): vol.All(int, vol.Range(min=1024, max=65535)),
                }
            ),
            errors=errors,
        )
```

**Step 4: Add reconfigure strings to `strings.json` and `translations/en.json`**

In the `config` → `step` section, add:

```json
      "reconfigure": {
        "title": "Reconfigure GQ GMC-500",
        "description": "Update the HTTP server port.",
        "data": {
          "port": "HTTP Server Port"
        }
      }
```

Also add abort reason for success:

```json
    "abort": {
      "already_configured": "This device is already configured",
      "reconfigure_successful": "Re-configuration was successful"
    }
```

**Step 5: Run tests**

```bash
.venv/bin/pytest tests/test_config_flow.py -v
```

**Step 6: Commit**

```bash
git add custom_components/gmc500/config_flow.py custom_components/gmc500/strings.json custom_components/gmc500/translations/en.json tests/test_config_flow.py
git commit -m "feat: add reconfiguration flow for port changes"
```

---

## Task 9: diagnostics.py (Gold)

**Files:**
- Create: `custom_components/gmc500/diagnostics.py`
- Create: `tests/test_diagnostics.py`

**Step 1: Write the failing test**

Create `tests/test_diagnostics.py`:

```python
"""Tests for GMC-500 diagnostics."""

import sys
from datetime import datetime
from unittest.mock import MagicMock

import pytest

# Reuse conftest mocks — already loaded via sys.modules
sys.modules.setdefault("homeassistant.components.diagnostics", MagicMock())

from custom_components.gmc500.diagnostics import async_get_config_entry_diagnostics
from custom_components.gmc500.coordinator import GMCCoordinator


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
```

**Step 2: Run to confirm failure**

```bash
.venv/bin/pytest tests/test_diagnostics.py -v
```

Expected: ModuleNotFoundError for `custom_components.gmc500.diagnostics`.

**Step 3: Create `custom_components/gmc500/diagnostics.py`**

```python
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
```

**Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_diagnostics.py -v
```

Expected: all pass.

**Step 5: Commit**

```bash
git add custom_components/gmc500/diagnostics.py tests/test_diagnostics.py
git commit -m "feat: add diagnostics platform"
```

---

## Task 10: stale-devices (Gold)

Allow users to manually remove devices from the device registry. Return `False` if the device is still actively sending data.

**Files:**
- Modify: `custom_components/gmc500/__init__.py`
- Modify: `tests/test_init.py`
- Modify: `tests/conftest.py`

**Step 1: Add `device_registry` mock to `conftest.py`**

```python
_ha_device_registry = MagicMock()
_ha_device_registry.DeviceEntry = MagicMock
sys.modules.setdefault("homeassistant.helpers.device_registry", _ha_device_registry)
```

Also add in `test_init.py`'s sys.modules block.

**Step 2: Write failing tests in `tests/test_init.py`**

```python
from custom_components.gmc500 import async_remove_config_entry_device  # noqa: E402


class TestRemoveDevice:
    """Tests for async_remove_config_entry_device."""

    @pytest.mark.asyncio
    async def test_allows_removal_of_inactive_device(self):
        """Inactive device (not in coordinator.devices) can be removed."""
        hass = MagicMock()
        entry = MagicMock()
        coordinator = MagicMock()
        coordinator.devices = {}  # No active data
        entry.runtime_data = MagicMock()
        entry.runtime_data.coordinator = coordinator

        device_entry = MagicMock()
        device_entry.identifiers = {("gmc500", "AID1_GID1")}

        result = await async_remove_config_entry_device(hass, entry, device_entry)

        assert result is True

    @pytest.mark.asyncio
    async def test_blocks_removal_of_active_device(self):
        """Active device (present in coordinator.devices) cannot be removed."""
        hass = MagicMock()
        entry = MagicMock()
        coordinator = MagicMock()
        coordinator.devices = {"AID1_GID1": {"CPM": 15.0}}
        entry.runtime_data = MagicMock()
        entry.runtime_data.coordinator = coordinator

        device_entry = MagicMock()
        device_entry.identifiers = {("gmc500", "AID1_GID1")}

        result = await async_remove_config_entry_device(hass, entry, device_entry)

        assert result is False
```

**Step 3: Run to confirm failures**

```bash
.venv/bin/pytest tests/test_init.py::TestRemoveDevice -v
```

**Step 4: Add `async_remove_config_entry_device` to `__init__.py`**

```python
from homeassistant.helpers import device_registry as dr


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
```

**Step 5: Run tests**

```bash
.venv/bin/pytest tests/test_init.py -v
```

**Step 6: Commit**

```bash
git add custom_components/gmc500/__init__.py tests/test_init.py tests/conftest.py
git commit -m "feat: add async_remove_config_entry_device for stale device removal"
```

---

## Task 11: log-when-unavailable (Silver)

Log at `INFO` level exactly once when a device goes offline and once when it comes back online.

**Files:**
- Modify: `custom_components/gmc500/coordinator.py`
- Modify: `tests/test_coordinator.py`

**Step 1: Write failing tests in `tests/test_coordinator.py`**

```python
import logging


class TestAvailabilityLogging:
    """Tests for once-only availability change logging."""

    def test_logs_device_online_after_offline(self, caplog):
        """Coordinator logs INFO when device comes back after being offline."""
        hass = MagicMock()
        coordinator = GMCCoordinator(hass)
        coordinator._availability_state["AID_GID"] = False  # Simulate offline

        with caplog.at_level(logging.INFO, logger="custom_components.gmc500.coordinator"):
            coordinator.process_data({
                "AID": "AID", "GID": "GID", "CPM": 10.0,
                "ACPM": 10.0, "uSV": 0.05,
            })

        assert any("available" in r.message.lower() for r in caplog.records)

    def test_does_not_log_if_already_online(self, caplog):
        """Coordinator does not log when device was already online."""
        hass = MagicMock()
        coordinator = GMCCoordinator(hass)
        coordinator._availability_state["AID_GID"] = True  # Already online

        with caplog.at_level(logging.INFO, logger="custom_components.gmc500.coordinator"):
            coordinator.process_data({
                "AID": "AID", "GID": "GID", "CPM": 10.0,
                "ACPM": 10.0, "uSV": 0.05,
            })

        assert not any("available" in r.message.lower() for r in caplog.records)

    def test_logs_device_offline_on_availability_check(self, caplog):
        """is_device_available logs INFO when device transitions to offline."""
        hass = MagicMock()
        coordinator = GMCCoordinator(hass)
        # Simulate device that was previously online but last seen 20 min ago
        from datetime import datetime, timedelta
        coordinator.devices["AID_GID"] = {
            "last_seen": datetime.now() - timedelta(minutes=20)
        }
        coordinator._availability_state["AID_GID"] = True  # Was online

        with caplog.at_level(logging.INFO, logger="custom_components.gmc500.coordinator"):
            result = coordinator.is_device_available("AID_GID")

        assert result is False
        assert any("unavailable" in r.message.lower() or "offline" in r.message.lower()
                   for r in caplog.records)

    def test_does_not_log_offline_repeatedly(self, caplog):
        """is_device_available does not repeat offline log on subsequent calls."""
        hass = MagicMock()
        coordinator = GMCCoordinator(hass)
        from datetime import datetime, timedelta
        coordinator.devices["AID_GID"] = {
            "last_seen": datetime.now() - timedelta(minutes=20)
        }
        coordinator._availability_state["AID_GID"] = False  # Already logged as offline

        with caplog.at_level(logging.INFO, logger="custom_components.gmc500.coordinator"):
            coordinator.is_device_available("AID_GID")

        assert not any("unavailable" in r.message.lower() or "offline" in r.message.lower()
                       for r in caplog.records)
```

**Step 2: Run to confirm failures**

```bash
.venv/bin/pytest tests/test_coordinator.py::TestAvailabilityLogging -v
```

**Step 3: Update `coordinator.py`**

Add `_availability_state: dict[str, bool]` to `__init__`:

```python
    def __init__(self, hass: Any) -> None:
        """Initialize coordinator."""
        self.hass = hass
        self.devices: dict[str, dict[str, Any]] = {}
        self._registered_devices: dict[str, str] = {}
        self._ignored_devices: set[str] = set()
        self._listeners: list[callable] = []
        self._availability_state: dict[str, bool] = {}
```

Update `process_data` to log online transitions:

```python
    def process_data(self, data: dict[str, Any]) -> None:
        """Store incoming device data and trigger forwarding."""
        aid = data[PARAM_AID]
        gid = data[PARAM_GID]
        device_id = self._device_id(aid, gid)

        if device_id in self._ignored_devices:
            return

        was_available = self._availability_state.get(device_id)
        data["last_seen"] = datetime.now()
        self.devices[device_id] = data

        if was_available is False:
            _LOGGER.info("GMC-500 device %s/%s is now available", aid, gid)
        self._availability_state[device_id] = True

        for listener in self._listeners:
            listener(device_id, data)

        self.hass.async_create_task(self.forward_to_gmcmap(data))
```

Update `is_device_available` to log offline transitions:

```python
    def is_device_available(self, device_id: str) -> bool:
        """Return True if the device was seen within the availability window."""
        if device_id not in self.devices:
            return False
        last_seen = self.devices[device_id].get("last_seen")
        if last_seen is None:
            return False
        available = (datetime.now() - last_seen).total_seconds() <= AVAILABILITY_TIMEOUT

        prev = self._availability_state.get(device_id)
        if prev is True and not available:
            _LOGGER.info(
                "GMC-500 device %s is now unavailable (no data for 15 minutes)",
                device_id,
            )
            self._availability_state[device_id] = False

        return available
```

**Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_coordinator.py -v
```

**Step 5: Commit**

```bash
git add custom_components/gmc500/coordinator.py tests/test_coordinator.py
git commit -m "feat: log device availability transitions once (online/offline)"
```

---

## Task 12: Documentation — Gold docs-* rules (Gold)

Update `README.md` to satisfy all 7 Gold documentation rules.

**Files:**
- Modify: `README.md`

**Step 1: Rewrite README.md with these sections**

The README must cover:
- `docs-high-level-description` — What the device/integration is
- `docs-installation-instructions` — Step-by-step install
- `docs-removal-instructions` — How to remove the integration
- `docs-configuration-parameters` — All config options
- `docs-data-update` — How/when data is updated
- `docs-supported-devices` — Known supported devices
- `docs-supported-functions` — All entities and features
- `docs-known-limitations` — Explicit limitations list
- `docs-troubleshooting` — Troubleshooting guide
- `docs-use-cases` — Practical use case examples
- `docs-examples` — Copy-paste automation examples

Write the following README:

```markdown
# GQ GMC-500 Home Assistant Integration

A Home Assistant custom integration for the [GQ Electronics GMC-500](https://www.gqelectronicsllc.com/) Geiger counter family. Receives radiation and environmental data **directly via WiFi** (local push, no cloud dependency) and optionally forwards readings to [gmcmap.com](http://www.gmcmap.com/).

## Supported Devices

| Device | Status |
|--------|--------|
| GQ GMC-500 | ✅ Supported |
| GQ GMC-500+ | ✅ Supported |
| GQ GMC-320 | ⚠️ Untested (same protocol, may work) |
| GQ GMC-600 | ⚠️ Untested (same protocol, may work) |

## Features

### Entities Created per Device

| Entity | Unit | Description |
|--------|------|-------------|
| CPM | CPM | Counts per minute (live) |
| Average CPM | CPM | Running average CPM *(diagnostic, disabled by default)* |
| Dose Rate | µSv/h | Equivalent dose rate |
| Temperature | °C | Ambient temperature *(if device reports it)* |
| Humidity | % | Relative humidity *(if device reports it)* |
| Atmospheric Pressure | hPa | Air pressure *(if device reports it)* |

### Other Features

- **Automatic device discovery** — new devices are detected when they first send data; you confirm or ignore them in the HA notification
- **gmcmap.com forwarding** — readings are asynchronously forwarded to gmcmap.com (3 retries with backoff); no blocking
- **Multi-device support** — one integration instance can receive data from multiple GMC-500 units on different AID/GID pairs

## Data Update Model

This integration uses a **local push** model. The GMC-500 device initiates an HTTP GET request to Home Assistant every ~5 minutes (configurable on the device). HA does not poll the device. Entities become **unavailable** if no data is received for 15 minutes (3× the default interval).

## Installation

### Prerequisites

- Home Assistant 2024.1 or newer
- GQ GMC-500 connected to your WiFi network
- The device's WiFi server feature configured to point at your HA instance

### HACS Installation (Recommended)

1. Open HACS → Integrations → ⋮ → Custom repositories
2. Add `https://github.com/volschin/gq_gmc-500` as type **Integration**
3. Search for "GQ GMC-500" and install it
4. Restart Home Assistant

### Manual Installation

1. Download or clone this repository
2. Copy `custom_components/gmc500/` into your HA `config/custom_components/` directory
3. Restart Home Assistant

### Device Configuration

On the GMC-500:
1. Go to **Menu → WiFi → WiFi Server**
2. Set **Server** to your HA instance IP (e.g. `192.168.1.10`)
3. Set **Port** to match what you'll configure in HA (default `8080`)
4. Enable the WiFi server

### Integration Setup

1. In HA, go to **Settings → Devices & Services → Add Integration**
2. Search for "GQ GMC-500"
3. Enter the HTTP port to listen on (default: `8080`, range: 1024–65535)
4. When your GMC-500 sends its first reading, a notification appears — confirm or ignore the device
5. Sensors appear automatically after confirmation

## Configuration Parameters

### Initial Setup

| Parameter | Default | Description |
|-----------|---------|-------------|
| HTTP Server Port | 8080 | Port HA listens on for GMC-500 data. Must be free and accessible from the device. |

### Options (reconfigurable)

| Parameter | Description |
|-----------|-------------|
| HTTP Server Port | Change the listening port. Takes effect after reload. |

To access options: **Settings → Devices & Services → GQ GMC-500 → Configure**

To reconfigure (change port without removing): click the **⋮** menu → **Reconfigure**

## Removal

1. Go to **Settings → Devices & Services → GQ GMC-500 → ⋮ → Delete**
2. Confirm deletion
3. The HTTP server is stopped immediately
4. Individual devices can be removed from the device registry via **Settings → Devices & Services → Devices** — select the device → **⋮ → Delete** (only available when the device is inactive)

## Use Cases

- **Home radiation monitoring** — track background radiation trends over time
- **Event detection** — automate alerts when CPM exceeds a threshold (e.g. smoke detector test, radon spike)
- **Data logging** — store readings in InfluxDB/Grafana via HA's recorder
- **gmcmap.com community sharing** — automatically contribute to the global radiation map

## Automation Examples

### Alert when radiation is elevated

```yaml
automation:
  - alias: "Radiation alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.gmc_500_0034021_cpm
        above: 100
    action:
      - service: notify.mobile_app_myphone
        data:
          message: "Radiation CPM is {{ states('sensor.gmc_500_0034021_cpm') }} — above normal!"
```

### Daily radiation summary

```yaml
automation:
  - alias: "Daily radiation log"
    trigger:
      - platform: time
        at: "20:00:00"
    action:
      - service: notify.notify
        data:
          message: >
            Today's radiation: CPM {{ states('sensor.gmc_500_0034021_cpm') }},
            dose rate {{ states('sensor.gmc_500_0034021_dose_rate') }} µSv/h
```

## Known Limitations

- **Device registration is not persisted** — if HA restarts, the coordinator's device registry is rebuilt from scratch. Known devices (those with confirmed config entries) continue to work; only the runtime "known" state is lost briefly until the first data packet arrives after restart.
- **No device authentication** — any HTTP client that sends correctly formatted requests to the configured port will be processed. Use firewall rules to restrict access if needed.
- **Single integration instance** — only one port can be configured. All GMC-500 devices must send to the same port (they are distinguished by AID/GID).
- **gmcmap.com forwarding requires account** — you must have a gmcmap.com account and configure your AID/GID on the device for forwarding to succeed.
- **No historical backfill** — if HA is offline when the device sends data, those readings are lost.

## Troubleshooting

### Entities show "Unavailable"

- Check that the GMC-500 WiFi server is enabled and pointing at the correct IP/port
- Verify the port is not blocked by a firewall
- Wait up to 15 minutes — the device only sends data every ~5 minutes by default
- Check HA logs for "GMC-500 device … is now unavailable"

### Port is already in use

- A repair issue will appear in HA: **Settings → Repairs**
- Change the port via **Settings → Devices & Services → GQ GMC-500 → Configure**
- Or stop the other process using that port

### Device not discovered after setup

- Ensure the device's WiFi server is enabled and pointed at HA's IP on the configured port
- Check HA logs for incoming requests: look for `/log2.asp` in the logs
- Confirm the device is sending to `http://<HA-IP>:<port>/log2.asp`

### gmcmap.com forwarding fails

- Check HA logs for "gmcmap.com forwarding failed" messages
- Verify your AID and GID are correct on the device settings
- gmcmap.com may be temporarily unreachable — forwarding retries 3 times with backoff

### Sensors not created after confirming device

- Sensors are created when the **first data packet** arrives after confirmation
- Wait 5–10 minutes for the device to send its next reading
- Check the device list: **Settings → Devices & Services → Devices** — search "GMC"
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: comprehensive documentation for HA Gold quality scale"
```

---

## Task 13: Boost test coverage to ≥95% (Silver)

Identify and fill coverage gaps. The goal is >95% line coverage across all integration modules.

**Step 1: Measure current coverage**

```bash
.venv/bin/pytest tests/ -v --cov=custom_components/gmc500 --cov-report=term-missing
```

Note which lines are not covered.

**Step 2: Add tests for uncovered lines**

Common gaps to check:
- `coordinator.py`: `unignore_device`, `_availability_state` first-ever-seen path
- `config_flow.py`: `async_step_reconfigure` (already covered by Task 8)
- `__init__.py`: `_async_update_listener`, `async_remove_config_entry_device` edge cases
- `server.py`: 404 path, non-numeric optional params

For each uncovered branch, write a targeted test in the appropriate test file. Example for `unignore_device`:

```python
def test_unignore_device_makes_it_processable(self):
    """Unignored device has its data processed again."""
    hass = MagicMock()
    coordinator = GMCCoordinator(hass)
    coordinator.ignore_device("AID", "GID")
    coordinator.unignore_device("AID", "GID")
    assert not coordinator.is_device_ignored("AID", "GID")
```

**Step 3: Re-run until coverage ≥95%**

```bash
.venv/bin/pytest tests/ --cov=custom_components/gmc500 --cov-report=term-missing
```

**Step 4: Commit**

```bash
git add tests/
git commit -m "test: boost coverage to >=95% for HA Gold quality scale"
```

---

## Task 14: Full suite + push (Final)

**Step 1: Run full test suite**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all tests pass, no warnings about deprecated patterns.

**Step 2: Verify coverage**

```bash
.venv/bin/pytest tests/ --cov=custom_components/gmc500 --cov-report=term-missing
```

Expected: ≥95% coverage.

**Step 3: Push to GitHub**

```bash
git push origin main
```

---

## Quality Scale Checklist After Implementation

| Rule | Tier | Status |
|------|------|--------|
| runtime-data | Bronze | ✅ Task 1 |
| test-before-setup | Bronze | ✅ Task 4 |
| entity-event-setup | Bronze | ✅ Task 5 |
| has-entity-name | Bronze | ✅ pre-existing |
| entity-unique-id | Bronze | ✅ pre-existing |
| config-flow | Bronze | ✅ pre-existing |
| unique-config-entry | Bronze | ✅ pre-existing |
| integration-owner | Silver | ✅ Task 2 |
| parallel-updates | Silver | ✅ Task 3 |
| log-when-unavailable | Silver | ✅ Task 11 |
| config-entry-unloading | Silver | ✅ pre-existing |
| entity-unavailable | Silver | ✅ pre-existing |
| test-coverage >95% | Silver | ✅ Task 13 |
| diagnostics | Gold | ✅ Task 9 |
| stale-devices | Gold | ✅ Task 10 |
| reconfiguration-flow | Gold | ✅ Task 8 |
| entity-translations | Gold | ✅ Task 6 |
| icon-translations | Gold | ✅ Task 6 |
| entity-category | Gold | ✅ Task 7 |
| entity-disabled-by-default | Gold | ✅ Task 7 |
| exception-translations | Gold | ✅ Task 4 |
| repair-issues | Gold | ✅ Task 4 |
| devices | Gold | ✅ pre-existing |
| dynamic-devices | Gold | ✅ pre-existing |
| discovery | Gold | ✅ pre-existing |
| docs-* (all 7) | Gold | ✅ Task 12 |
