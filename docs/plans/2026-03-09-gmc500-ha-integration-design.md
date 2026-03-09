# GQ GMC-500 Home Assistant Integration — Design

## Ziel

Custom Integration für Home Assistant, die Messdaten eines GQ GMC-500 Geigerzählers
direkt per WiFi empfängt (statt über die Cloud) und lokal als HA-Entities bereitstellt.
Die Daten werden zusätzlich an gmcmap.com weitergeleitet. Die lokale Funktion ist
cloud-unabhängig — Ausfälle von gmcmap.com haben keine Auswirkung auf HA.

## Protokoll

Der GMC-500 sendet periodisch HTTP GET Requests:

```
GET /log2.asp?AID=<AccountID>&GID=<DeviceID>&CPM=<cpm>&ACPM=<acpm>&uSV=<usv>[&tmp=<temp>&hmdt=<humidity>&ap=<pressure>]
```

Parameter:
- `AID` — Account ID (numerisch)
- `GID` — Geiger Counter ID (numerisch)
- `CPM` — Counts Per Minute (numerisch)
- `ACPM` — Average CPM (numerisch)
- `uSV` — µSv/h Dosisleistung (numerisch)
- `tmp` — Temperatur °C (optional)
- `hmdt` — Feuchtigkeit % (optional)
- `ap` — Luftdruck hPa (optional)

Erwartete Response: `OK.ERR0` (Erfolg), HTTP 200.

## Architektur

Standalone `aiohttp`-Webserver innerhalb der HA-Integration auf konfigurierbarem Port
(Default 8080). Der GMC-500 wird konfiguriert mit Server = `<HA-IP>:<Port>`, URL = `log2.asp`.

```
GMC-500 ──GET /log2.asp──► server.py ──► coordinator.py ──► sensor.py (HA Entities)
                              │                 │
                              │ "OK.ERR0"       └──async──► gmcmap.com/log2.asp
                              │  (sofort)                   (Retry 3x, entkoppelt)
                              ▼
                           GMC-500
```

Schlüsselprinzip: Response an den GMC-500 erfolgt sofort, bevor die gmcmap.com-Weiterleitung
stattfindet. Lokale Erfassung ist nie von der Cloud abhängig.

## Komponentenstruktur

```
custom_components/gmc500/
├── __init__.py          # Integration Setup, HTTP-Server Lifecycle
├── manifest.json        # HA Integration Metadata
├── config_flow.py       # UI-Konfiguration (Port, Device Discovery, Options)
├── const.py             # Konstanten (Domain, Default-Port, Parameter-Namen)
├── server.py            # aiohttp HTTP-Server (empfängt GMC-500 Requests)
├── coordinator.py       # Daten-Koordination, gmcmap.com Forwarding
├── sensor.py            # Sensor-Entities (CPM, ACPM, µSv/h, tmp, hmdt, ap)
├── strings.json         # UI-Texte für Config Flow
└── translations/
    └── en.json          # Englische Übersetzungen
```

| Modul | Verantwortung |
|-------|---------------|
| `__init__.py` | Startet/stoppt HTTP-Server beim Laden/Entladen der Integration |
| `server.py` | aiohttp-Server, parst log2.asp GET-Requests, validiert Parameter, ruft Coordinator-Callbacks auf |
| `coordinator.py` | Hält aktuellen Zustand pro Gerät (AID/GID), leitet Daten async an gmcmap.com weiter, verwaltet Device-Discovery |
| `sensor.py` | Erstellt Sensor-Entities pro Gerät, aktualisiert Werte bei neuen Messdaten |
| `config_flow.py` | Initiale Konfiguration (Port), Device-Bestätigung bei Auto-Discovery, Options Flow |

## Entities & Device-Modell

Pro AID/GID-Paar wird ein HA-Device angelegt:
- `identifiers`: `{("gmc500", "<AID>_<GID>")}`
- `name`: `GMC-500 <GID>` (im Config Flow änderbar)
- `manufacturer`: `GQ Electronics`
- `model`: `GMC-500`

### Sensor-Entities

| Entity | Device Class | State Class | Unit | Anmerkung |
|--------|-------------|-------------|------|-----------|
| CPM | — | `measurement` | `CPM` | Immer vorhanden |
| ACPM | — | `measurement` | `CPM` | Immer vorhanden |
| µSv/h | — | `measurement` | `µSv/h` | Immer vorhanden |
| Temperatur | `temperature` | `measurement` | `°C` | Nur wenn `tmp` geliefert |
| Feuchtigkeit | `humidity` | `measurement` | `%` | Nur wenn `hmdt` geliefert |
| Luftdruck | `atmospheric_pressure` | `measurement` | `hPa` | Nur wenn `ap` geliefert |

- Keine native HA `device_class` für Strahlung vorhanden
- `state_class: measurement` ermöglicht HA Long-Term Statistics
- Optionale Entities werden erst beim ersten Empfang des Parameters angelegt

## Config Flow

### Schritt 1: Initiale Einrichtung
- Eingabe: HTTP Server Port (Default 8080)
- Validierung: Port frei, Bereich 1024–65535
- Nur eine Integration-Instanz möglich (ein Server, mehrere Geräte)

### Schritt 2: Device Discovery (automatisch)
- Bei unbekanntem AID/GID-Paar: HA-Discovery-Notification
- Zeigt AID, GID und ersten Messwert
- Benutzer kann Gerätenamen anpassen
- "Bestätigen" → Device + Entities werden angelegt
- "Ignorieren" → AID/GID auf Ignore-Liste

### Schritt 3: Options Flow
- Port änderbar (löst Server-Neustart aus)
- Ignorierte Geräte können wieder freigegeben werden

## gmcmap.com Forwarding

- AID/GID aus dem Geräte-Request werden 1:1 an gmcmap.com durchgereicht
- Forwarding läuft als `asyncio.Task`, entkoppelt vom Request/Response-Zyklus
- Retry: 3 Versuche mit exponentiellem Backoff (1s → 2s → 4s)
- Timeout pro Request: 10 Sekunden
- Bei endgültigem Fehlschlag: Warning loggen, keine weitere Aktion

## Fehlerbehandlung

| Fehlerfall | Verhalten | Auswirkung auf HA |
|------------|-----------|-------------------|
| Ungültige Parameter vom GMC-500 | `OK.ERR0` zurück, Daten verwerfen, Warning loggen | Keine |
| gmcmap.com nicht erreichbar | 3x Retry, dann Warning loggen | Keine — Entities unberührt |
| gmcmap.com antwortet mit Fehler | Warning loggen mit Response-Body | Keine |
| Port kann nicht gebunden werden | Config Flow zeigt Fehler | Integration startet nicht |
| HA fährt herunter | HTTP-Server wird sauber gestoppt | Graceful Shutdown |
| GMC-500 sendet nach langer Pause | Entities aktualisiert, availability → true | Sensor wieder verfügbar |

## Availability

- Gerät gilt als `unavailable` wenn >15 Minuten kein Request kam (3× Standard-Intervall von 5 Min)
- Beim nächsten Request → wieder `available`

## HACS-Kompatibilität

- Standardstruktur für `custom_components/`
- `hacs.json` mit Metadaten für HACS-Installation

## Entscheidungen

| Entscheidung | Gewählt | Alternativen verworfen |
|--------------|---------|----------------------|
| HTTP-Server | Standalone aiohttp auf eigenem Port | HA Webhook, HA HTTP-View |
| Konfiguration | Config Flow (UI) | YAML, Hybrid |
| Multi-Device | Ein Server, AID/GID-basierte Unterscheidung | Ein Port pro Gerät |
| Device Discovery | Auto-Discovery mit Bestätigung | Voll-automatisch, manuell |
| gmcmap Credentials | AID/GID durchreichen | Separate Credentials, pro-Gerät optional |
| Retry-Strategie | 3x mit exponentiellem Backoff | Fire-and-forget, Queue mit Nachlieferung |
