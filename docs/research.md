# Research: sources and decisions

## Sources

| Source | Used for | Trust |
| --- | --- | --- |
| Own analysis of the softener (Oct 2026): AdGuard query log, FritzBox WLAN capture, mitmproxy reverse-proxy test | Hosts, polling interval, TLS parameters (1.2, no SNI, RSA kx), acceptance of a private-CA certificate, request shapes, firmware check | Primary, measured on this unit (SLPS 2.0) |
| [Richard-Schaller/syrlex2mqtt](https://github.com/Richard-Schaller/syrlex2mqtt) `doc/syrconnect-protocol.md` | Getter list and meanings, message format, `setSIR` semantics | Secondary; measured on SLPS 1.7/1.9. Code **not** run (see [upstream-review.md](upstream-review.md)) |
| [alexhass/syr_connect](https://github.com/alexhass/syr_connect) (HA cloud integration) | Entity semantics, LEXplus10S profile (`devices/lexplus10s.py`), units (`getFLO` in l/h, `getPRS` / 10), `getLAR` as local wall time | Secondary; very active, real-device fixtures. Read only, not run. Not usable directly: cloud only for LEXplus, and it has write entities |
| [eifel-tech/ioBroker.syrconnect](https://github.com/eifel-tech/ioBroker.syrconnect) | Confirms the fake-cloud approach and the same endpoints (`/WebServices/…asmx/GetBasicCommands`, `GetAllCommands`, plus root aliases) | Secondary; read only |
| Home Assistant 2026.10.4 source and the Supervisor discovery API | Config flow, coordinator and discovery patterns | Primary for API behaviour |

## Decisions

### Fake cloud instead of proxy

The real cloud answered `GetAllCommands` with an empty document during the whole
capture, so passively watching it yields no readings. Proxying would also pass
cloud `set` commands through to the softener. SYR Local therefore replaces the
cloud entirely and can only ever send getters.

### Only getters, and no `getSIR`

Any `set*` is executed by the softener. SIR is the regeneration trigger (`setSIR`
with `0` starts a regeneration), so even its getter is excluded. The check sits in
the response builder, not just in the catalog, so a future catalog edit cannot
bypass it.

### Firmware and maintenance are always 404

The firmware catalog `scf.cfg` lists SLPS 2.3 while the unit runs 2.0. Serving it
could trigger an update, as in syrlex2mqtt PR/issue #10, which serves it on
purpose. `maintenance.syrconnect.de` never completes TLS against the real server
and is not needed for readings.

### Tolerant regex instead of an XML parser

The softener sends literal `\r\n` and `\"` sequences, so strict parsers reject its
bodies. A regex also rules out entity-expansion attacks without needing
`defusedxml` (the add-on is stdlib-only).

### Text encoding: UTF-8, falling back to iso-8859-2

The handoff decodes bodies as iso-8859-2, and syrlex2mqtt shows Polish text that
was not valid UTF-8 (`po��czono`). The XML prolog, however, claims utf-8.
SYR Local tries strict UTF-8 first and falls back to iso-8859-2. Polish text in
iso-8859-2 practically never forms valid UTF-8, so both cases decode correctly.
ASCII values (all numeric getters) are identical either way. Only `getSTA`
could be affected.

### `getFLO` is L/h (assumption)

syrlex2mqtt documents L/min, alexhass/syr_connect maps it to L/h with
`device_class: volume_flow_rate`. alexhass has newer real-device data, so SYR
Local uses L/h and names the key `flow_lph`. Not yet confirmed on this unit;
compare against a known flow (for example a tap running into a measuring jug).

### `getLAR` is local wall time

alexhass documents (known issue 5 of their XML API notes) that the softener
counts seconds of its **local** clock, not UTC: 1792718160 is 23 Oct 2026 01:16
local time. SYR Local interprets the epoch as wall time in the Home Assistant
time zone (the Supervisor passes it as `TZ`) and converts it to UTC. Without
`TZ`, UTC is assumed. This deviates from a naive "epoch → UTC" conversion on
purpose; if it turns out wrong on this unit, change `_local_timestamp` in
`server/mapping.py`.

### `getPRS` = 255 means invalid

Per syrlex2mqtt, 255 indicates no valid pressure reading. Without a pressure
sensor (`getPST` = 1) the value mirrors the configured pressure, so the
pressure entity is disabled by default.

### Legacy TLS ciphers

The softener was captured using TLS 1.2 with RSA key exchange (`AES256-SHA`).
Python's default server cipher list on Alpine (OpenSSL 3.5) does **not** include
it (verified in the container), so the add-on sets `DEFAULT:@SECLEVEL=1`. TLS 1.3
remains available for other clients; TLS 1.0/1.1 are refused.

### Certificate

The softener accepted a mitmproxy-CA-signed leaf in the capture. SYR Local
generates its own CA and leaf (RSA 2048, SHA-256, 10 years, SANs `syrconnect.de`,
`*.syrconnect.de`, `IP:212.77.236.30`) and serves leaf + CA as the chain. That a
freshly generated private CA is accepted the same way is likely, but not yet
tested on the device.

### Ports and network

The device endpoint listens on 8443 inside the container and is published on host
port 443, so nothing needs root-only ports inside the container. The state API on
8099 is only on the internal Supervisor network. The add-on still runs as root
inside its container because `/data` is root-owned. It requests no privileges, no
host network and no Supervisor API role. Discovery and `addons/self/info` work
with the default add-on token.

### Persistence

Only `{serial, model}` is persisted (`/data/identity.json`) so discovery can be
re-sent right after a restart. Readings are not persisted: a restored stale
value would look current to Home Assistant.

### Home Assistant specifics (verified against 2026.10.4)

- `async_setup_entry` must return `True`. HA 2026.10 still logs an error and
  fails setup when it returns anything other than a bool
  (`config_entries.py`: "did not return boolean").
- Config flow schemas use `probatio` (HA's voluptuous successor used by core in
  2026.10) and `cv.port`.
- `device_registry.async_get_device` is deprecated; tests use
  `async_get_device_by_identifier`.

## Rejected alternatives

| Alternative | Why not |
| --- | --- |
| syrlex2mqtt | Write path via MQTT, XML injection, committed private key, outdated deps (see upstream-review) |
| alexhass/syr_connect in cloud mode | Keeps the cloud dependency; LEXplus is cloud-only there; exposes write entities |
| Local API on port 5333 | Closed on this unit (connection refused) |
| HA `rest` sensors on the add-on JSON | Works, but no device registry, discovery or availability handling; the integration replaces it |
| MQTT | Extra broker, retained-message replay risks; not needed for a read-only data path |
