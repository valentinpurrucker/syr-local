<img src="assets/icon.svg" width="64" height="64" alt="">

# SYR Local

Strictly read-only, cloud-free Home Assistant support for the **SYR LEXplus10S
Connect** water softener.

SYR Local has two parts that ship together:

- **Add-on "SYR Local"** (`syr_local/`). Stands in for `syrconnect.de` on your
  network. The softener's regular cloud polling arrives here instead, and the
  add-on answers with read-only `get` commands only.
- **Integration "SYR Local"** (`custom_components/syr_local/`). Discovered
  automatically from the add-on. Creates read-only sensors for salt, flow,
  capacity, water consumption, regeneration and more, and ships a compact
  dashboard card.

```
SYR LEXplus10S ──TLS :443──▶ SYR Local add-on ──HTTP :8099──▶ SYR Local integration
                            (getters only)                   (sensors, binary sensor)
```

> **Status:** running against a real LEXplus10S. The `getFLO` unit and the
> time zone of `getLAR` are still unconfirmed. See
> [What has been verified](#what-has-been-verified).

## Safety guarantees

The softener executes whatever commands the server sends, so the add-on is
built to never send anything that could change the device:

- **Getters only.** Every outgoing command must match `^get[A-Z0-9]{2,4}$` and
  carries an empty value. Anything else raises, and nothing is sent.
- **No regeneration trigger.** `getSIR` and every `set*` command are refused,
  even if someone adds them to the catalog by mistake.
- **No firmware updates.** Every `GET`, including the firmware check
  `/firmware/saocal2/scf.cfg`, returns 404.
- **No cloud.** Nothing is proxied or forwarded to SYR. There is no MQTT and no
  outbound connection apart from Supervisor discovery.
- **Read-only integration.** It only has sensor and binary sensor entities: no
  services, switches, buttons, selects or numbers.
- **Bounded input.** Requests are capped at 64 KB, command count and value
  length are capped too, and there is an optional source-IP allowlist. Bodies
  are parsed with a tolerant regex, so no XML entities are ever expanded.

## Installation (short version)

1. Add this repository to the Home Assistant add-on store and install **SYR Local**.
2. Start the add-on. It creates its own certificate on first start.
3. Install the integration: either add this repository to HACS as a custom
   integration repository, or copy `custom_components/syr_local` into your
   `config/custom_components/`. Then restart Home Assistant.
4. Point the DNS names `syrconnect.de` and `*.syrconnect.de` at your Home
   Assistant host (for example with AdGuard Home rewrites and FritzBox
   rebind-protection exceptions).
5. Within about a minute the add-on sees the softener. Home Assistant then
   offers **SYR Local** under *Settings → Devices & services → Discovered*.

Full instructions, including rollback and the port 443 conflict, are in
[docs/install.md](docs/install.md).

## Entities

| Entity | Unit | Notes |
| --- | --- | --- |
| Salt supply | weeks | `getSS1` |
| Salt amount | kg | `getSV1` |
| Water flow | L/h | `getFLO` (unit assumed L/h, see [research](docs/research.md)) |
| Remaining capacity | L | `getRES` |
| Total water consumption | L | `getCOF`, total increasing (Energy dashboard compatible) |
| Resin capacity | % | `getCS1` |
| Regeneration | on/off | `getRG1` |
| Water pressure | bar | `getPRS` / 10; diagnostic, disabled by default |
| Last regeneration | timestamp | `getLAR`; diagnostic |
| Regenerations | count | `getTOR`; diagnostic, disabled by default |
| Status message, Alarm | text | `getSTA`, `getALM`; diagnostic |

Entities become unavailable when the add-on cannot be reached, it reports a
different serial number, or the softener has not been heard from for 5 minutes.

## Dashboard card

The integration serves and loads a card of its own, so there is nothing extra
to install (no HACS frontend repository, no dashboard resource). It packs the
whole device into one card: status (ready, regenerating, alarm, offline), resin
charge with soft water left, salt with weeks left, current flow, today's water
use, the last regeneration, an hourly water graph for the last 24 hours and the
lifetime counters. Tap any value for its history.

```yaml
type: custom:syr-local-card
# all optional:
device: <device id>        # defaults to the first SYR Local device
name: Water softener
salt_warning_weeks: 3      # salt tile turns amber at or below, red at 1 week
show_graph: true
```

It also appears in the card picker as **SYR Local** with a visual editor.
The card, the integration and the add-on options are available in English and
German; the card follows the language of the Home Assistant user.
Entities are found through the device, so renaming entity IDs does not break
it. Colours follow the theme; with card-mod you can override
`--syr-accent`, `--syr-ok`, `--syr-warning`, `--syr-error` and
`--syr-tile-background`. "Today" and the graph come from the long-term
statistics of *Total water consumption*, so they fill in after the first hour.

## Documentation

- [docs/install.md](docs/install.md): installation, DNS redirect, rollback, troubleshooting
- [docs/architecture.md](docs/architecture.md): components, modules, data flow
- [docs/protocol.md](docs/protocol.md): the SYR Connect polling protocol and how SYR Local answers it
- [docs/state-api.md](docs/state-api.md): the versioned add-on ↔ integration contract
- [docs/research.md](docs/research.md): sources and design decisions
- [docs/upstream-review.md](docs/upstream-review.md): security review of the upstream syrlex2mqtt project

## What has been verified

On the real device: the softener connects to the add-on through the DNS
redirect and all readings appear in Home Assistant.

Without the physical device:

- 128 add-on and contract tests (`pytest`): tolerant parsing, the read-only
  response builder, routing (basic, full, empty, firmware 404, maintenance
  404), the state contract, certificates, config and discovery against a fake
  Supervisor.
- 36 integration tests on Home Assistant 2026.10.4 (`pytest-homeassistant-custom-component`):
  config flow (user, hassio, reconfigure), setup and unload, entities and
  device registry, availability, diagnostics redaction, the API client, the
  German translation and serving the dashboard card.
- The add-on Docker image (`python:3.13-alpine`, OpenSSL 3.5) builds and
  starts. A TLS 1.2 `AES256-SHA` handshake succeeds with `openssl s_client`,
  and the firmware request returns 404.

Not verified yet: the `getFLO` unit and the time zone of `getLAR` on this unit,
and Supervisor discovery on a real Home Assistant OS installation.

## Development

```sh
python3 -m pytest tests --ignore=tests/integration      # add-on + contract, stdlib + pytest
python3.14 -m pytest tests/integration                  # needs pytest-homeassistant-custom-component + home-assistant-frontend
```

See [docs/architecture.md](docs/architecture.md) before changing code.

## Disclaimer

Not affiliated with SYR (Hans Sasserath GmbH & Co. KG). Use at your own risk.
