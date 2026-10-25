# Security review: syrlex2mqtt (upstream)

Preserved from an earlier review in this repository. It explains why SYR Local
does not reuse syrlex2mqtt's code. SYR Local reuses only its protocol
documentation.

Source reviewed: https://github.com/Richard-Schaller/syrlex2mqtt (MIT, single
author, last commit 2024-10). The code was read, not run.

## Verdict

The upstream code is not overtly malicious (no eval/exec/telemetry, only MQTT +
HTTP), but it is **not safe to run as-is in a home**. It requires root, ships a
publicly known TLS private key, has no input validation (XML injection into
device responses) and outdated dependencies with known CVEs. Its guide also
requires DNS hijacking and suggests an optional firmware downgrade (bricking
risk).

## Findings

1. **Runs as root** (README: "switching to root user is necessary"). Binding
   80/443 as root gives the process full privileges; a bug or compromised
   dependency means full host compromise.
2. **Published private key** (`server.key` in the repo). Anyone can impersonate
   the bridge or intercept traffic.
3. **Outdated dependencies with CVEs** (express 4.18.2, body-parser 1.20.1, qs,
   path-to-regexp 0.1.7, cookie 0.5.0, send, ...). An audit reported 14
   vulnerabilities (5 high).
4. **No input validation / XML injection.** Values from MQTT messages and device
   XML are interpolated into XML attributes without escaping
   (`'<c n="' + setter + '" v="' + value + '"/>'`, around `syrlex2mqtt.js:402`,
   `:412`, `:585`, `:588`). A malicious MQTT publisher can inject arbitrary
   commands, including setters, into the device response.
5. **Built-in write path.** MQTT topics `syr/<id>/set_*` trigger regeneration,
   salt changes, schedules and (on SL models) the shut-off valve. It subscribes
   to `syr/#`, so retained `set` messages are replayed on restart.
6. **No authentication on HTTP endpoints.** Any host on the LAN can POST fake
   device data. There is no source-IP filtering, no rate limiting and no
   body-size limit. Device-supplied values end up in MQTT topic names.
7. **Firmware.** The guide documents a firmware downgrade (can brick the
   device). PR/issue #10 ("Support for SLPS 2.3") serves SYR's `scf.cfg`
   firmware catalog, which can trigger a firmware update.
8. **Valve control is safety-critical.** An MQTT compromise or bad automation
   can shut off the home's water supply on SL models.

## How SYR Local addresses these

| Upstream issue | SYR Local |
| --- | --- |
| Root, ports 80/443 | Container listens on 8443; the Supervisor maps host 443 → 8443. No privileges or host network requested |
| Published key | CA and leaf generated per installation on first start; keys `0600` under `/data/certs`; `*.key` gitignored |
| Dependencies | Add-on is Python stdlib only; integration uses only HA-provided `aiohttp`/`yarl`/`probatio` |
| XML injection | Response names validated against `^get[A-Z0-9]{2,4}$`, values always empty; no device value is ever echoed into a response |
| Write path | None exists: no MQTT, no services, no set commands, `getSIR` refused |
| Unauthenticated listeners | Device endpoint: only two POST paths, 64 KB cap, bounded parsing, optional IP allowlist. State API: read-only GET, internal network only |
| Firmware | Every GET returns 404; nothing is proxied |
