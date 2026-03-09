# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Home Assistant custom integration for the GQ Electronics GMC-500 Geiger counter. Receives radiation data directly via WiFi (local push, no cloud dependency) and forwards to gmcmap.com asynchronously.

## Build & Test Commands

```bash
# Run all tests
.venv/bin/pytest tests/ -v

# Run a single test file
.venv/bin/pytest tests/test_server.py -v

# Run a specific test
.venv/bin/pytest tests/test_server.py::test_server_responds_ok -v
```

No build step required — this is a Python custom component installed directly into Home Assistant.

## Architecture

### Data Flow

```
GMC-500 → GET /log2.asp → server.py → coordinator.py → sensor.py (HA Entities)
                              ↓                ↓
                         "OK.ERR0"        async → gmcmap.com (retry 3x)
```

The device always gets an immediate response. gmcmap.com forwarding is fire-and-retry in a background task.

### Key Modules

- **`server.py`** — Standalone `aiohttp` HTTP server on configurable port. Parses `log2.asp` GET requests with parameters AID, GID, CPM, ACPM, uSV (required) and tmp, hmdt, ap (optional). Calls a data callback.
- **`coordinator.py`** — Device state management keyed by `{AID}_{GID}`. Handles device registration, ignore lists, availability tracking (15min timeout), listener notifications, and gmcmap.com forwarding with 3x exponential backoff retry.
- **`sensor.py`** — `SensorEntity` subclasses for radiation (CPM, ACPM, µSv/h) and environment (temperature, humidity, pressure) data. Entities are created dynamically when a registered device first sends data.
- **`config_flow.py`** — Config Flow for port setup. Device discovery flow triggered when unknown AID/GID arrives — user confirms or ignores. Options flow for port changes.
- **`__init__.py`** — Integration lifecycle: starts/stops HTTP server, wires data callback to coordinator, triggers discovery flows for unknown devices.

### GMC-500 Protocol

The device sends HTTP GET to `/log2.asp?AID=<id>&GID=<id>&CPM=<n>&ACPM=<n>&uSV=<n>`. Server must respond with `OK.ERR0`. No authentication, no handshake.

## Testing Approach

homeassistant is **not installed** in the dev environment. All HA modules are mocked via `sys.modules` in `tests/conftest.py`. Tests for server.py and coordinator.py use real aiohttp and asyncio. Tests for sensor.py, config_flow.py, and __init__.py mock HA base classes.

Key fixture: `unused_tcp_port` (in conftest.py) provides a free port for server tests.

## Constants

All protocol constants, parameter names, and configuration keys are in `const.py`. Domain is `gmc500`.
