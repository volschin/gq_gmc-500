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
