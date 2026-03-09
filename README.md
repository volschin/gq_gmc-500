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
