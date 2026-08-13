# gq_gmc-500 repository notes

Home Assistant custom integration receiving local GMC-500 Wi-Fi pushes and
forwarding them asynchronously to gmcmap.com.

## Commands

```bash
.venv/bin/python -m py_compile custom_components/gmc500/*.py
.venv/bin/ruff check custom_components/ tests/
.venv/bin/pytest tests/ -v
.venv/bin/pytest --cov=custom_components.gmc500 --cov-report=term-missing -v
```

Home Assistant is mocked through `tests/conftest.py`; do not require a live HA
instance or install HA merely for these tests. CI's coverage floor is 80%.

## Invariants

- The device calls `/log2.asp` with required `AID`, `GID`, `CPM`, `ACPM`, `uSV`
  and optional `tmp`, `hmdt`, `ap`; respond immediately with `OK.ERR0`.
- Device identity is `{AID}_{GID}`. Unknown devices enter the discovery flow;
  ignored identities stay ignored.
- gmcmap forwarding must never delay the device response. Keep it in a background
  task with bounded retries.
- Entities are created only after a registered device first supplies data, and
  availability expires after the configured timeout.
- Keep protocol/config keys in `const.py` and preserve cleanup of the aiohttp
  server and background tasks on unload/reload.

When entity metadata, config flow or diagnostics change, keep translations,
manifest, HACS/hassfest metadata and tests aligned.
