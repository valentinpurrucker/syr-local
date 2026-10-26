# Architecture

SYR Local is one product made of two parts that share one versioned contract:

```
 SYR LEXplus10S ──TLS:443──▶ add-on "SYR Local" ──HTTP:8099──▶ integration "SYR Local"
  (polls every ~11 s)        (stands in for syrconnect.de)       (DataUpdateCoordinator, 30 s)
                              │                                   │
                              └── Supervisor discovery ──────────▶ config flow (hassio step)
```

The device always initiates. It POSTs to what it believes is `syrconnect.de`
(DNS points it at the add-on). The add-on answers with a list of commands. It
only ever sends read-only `getXXX` commands with an empty value, and the device
returns the values in its next request. The add-on turns the raw getter values
into a small semantic state document. The integration polls that document and
creates read-only entities.

## Safety model (read-only by construction)

| Rule | Where it is enforced |
| --- | --- |
| Only `get[A-Z0-9]{2,4}` with `v=""` is ever sent | `server/catalog.py::ensure_read_only`, called by `server/protocol.py::build_response` for every command. Anything else raises and nothing is sent. |
| `getSIR` (regeneration trigger) and every `set*` are never sent | Hard-coded in `catalog.FORBIDDEN`; the regex already rejects `set*`; tests check the catalog and the builder |
| No firmware update | Every `GET` (including `/firmware/saocal2/scf.cfg`) returns 404; there is no proxy and no outbound connection to the cloud |
| `maintenance.*` is ignored | Any request whose `Host` starts with `maintenance.` returns 404 |
| Only the two ASMX endpoints are served | Exact path match on POST; everything else returns 404 |
| Bounded input | 64 KB body cap, at most 512 commands, values longer than 512 characters are dropped, only catalog getter names are kept (bounded memory), optional source-IP allowlist, tolerant regex parsing (no XML parser, no entity expansion) |
| Integration cannot write | No services and no switch/button/select/number platforms; the HTTP client only issues `GET /api/v1/state` |

## Add-on (`syr_local/server/`)

Domain layer (pure, no I/O, unit-tested without a network):

| Module | Responsibility |
| --- | --- |
| `catalog.py` | Getter lists (`BASIC_GETTERS`, `FULL_GETTERS` for LEXplus10S), `FORBIDDEN`, `ensure_read_only()` |
| `protocol.py` | `parse_request_body(bytes) -> dict[str, str]` (tolerant regex, form field `xml=`, UTF-8 with iso-8859-2 fallback, HTML-unescape, bounds) and `build_response(names) -> str` |
| `planner.py` | `CommandPlanner`: answers `GetBasicCommands` with the basic getters and `GetAllCommands` with the full catalog at most once per poll interval, otherwise with nothing |
| `mapping.py` | Raw getter map → `device` identity and semantic `values` (table-driven, one row per value key) |
| `state.py` | `DeviceState`: thread-safe in-memory store (raw getters, last seen/read, request count) and `state_document()` which renders the versioned JSON contract |

Infrastructure layer:

| Module | Responsibility |
| --- | --- |
| `config.py` | Read and validate `/data/options.json` into a frozen `Config` |
| `certs.py` | Create (once) and load the local CA + leaf under `/data/certs`; build the TLS context |
| `device_server.py` | TLS HTTP server on `0.0.0.0:8443` that routes device requests to the domain layer |
| `state_api.py` | Plain HTTP server on `0.0.0.0:8099`: `GET /api/v1/state`, `GET /health` |
| `storage.py` | Persist only the device identity (`/data/identity.json`) |
| `discovery.py` | Supervisor discovery (`POST http://supervisor/discovery`) with retries |
| `app.py` / `__main__.py` | Wiring, logging, signals |

Data flow for one device request:

1. `device_server` checks the source IP, method, `Host` and path, then reads at most 64 KB.
2. `protocol.parse_request_body` extracts `{getter: value}` pairs.
3. `DeviceState.record` merges them and updates `last_seen`, `last_read` and the request count. If the serial changed, the app persists the identity and announces discovery.
4. `CommandPlanner.commands_for(endpoint)` picks the getters to request next.
5. `protocol.build_response` validates every name and renders the XML reply.

The state API calls `state_document(snapshot, now, tz)`, which applies `mapping` on
every request. Raw values stay internal; they are only logged at debug level.

## Shared contract

`GET /api/v1/state` with `schema_version: 1` is the only interface between the two
parts (see [state-api.md](state-api.md)). Both sides define the same value keys:
`syr_local/server/mapping.py::VALUE_KEYS` and
`custom_components/syr_local/models.py::VALUE_TYPES`. A test
(`tests/test_contract.py`) fails if they drift apart or if the schema versions
differ. Add-on and integration always share one version number.

## Integration (`custom_components/syr_local/`)

| Module | Responsibility |
| --- | --- |
| `models.py` | Pure parsing/validation of the state payload into `SyrLocalState` / `DeviceInfo` (no HA imports) |
| `api.py` | `SyrLocalClient`: aiohttp `GET /api/v1/state`, 10 s timeout, typed errors |
| `coordinator.py` | `DataUpdateCoordinator[SyrLocalState]`, 30 s; rejects a different serial than the config entry; `device_online` = last seen within 5 min |
| `entity.py` | `SyrLocalEntity` base: device registry info, unique ID `{serial}_{key}`, availability |
| `sensor.py`, `binary_sensor.py` | One description tuple and one generic class per platform |
| `config_flow.py` | `user`, `hassio` (+ confirm) and `reconfigure` steps |
| `diagnostics.py` | Redacted state and coordinator status |
| `frontend.py` | Serves `frontend/syr-local-card.js` at `/syr_local/syr-local-card.js` and adds it to every frontend page load (`async_setup`, once per start; `?v=<content hash>` busts the browser cache whenever the file changes) |
| `frontend/syr-local-card.js` | `custom:syr-local-card`: one plain web component, no build step. Finds the device's entities by platform and translation key in `hass.entities`, reads `hass.states` only, and fetches hourly water use from the recorder statistics of `total_water_l`. Read-only like the rest |

Discovery: when the add-on has seen `getSRN`, it sends
`{"host": <addon hostname>, "port": 8099, "serial": <serial>}` for the service
`syr_local`. HA starts the integration's `hassio` step. The flow uses the serial
as its unique ID, so a second announcement updates host/port instead of creating
a duplicate. The manual `user` step does the same with a host and port the user
enters.

## Design choices

- **Stdlib only in the add-on.** `http.server`, `ssl` and `subprocess` (for `openssl`
  certificate generation) cover everything. This keeps the attack surface small.
- **No XML parser.** The device sends literal `\r\n` and `\"` sequences, so a strict
  parser fails anyway. A regex cannot expand entities.
- **Readings are not persisted.** Only the identity survives a restart (so discovery
  can be sent at once). After a restart `values` is empty until the device answers.
- **No multi-device abstraction.** The catalog and the mapping table are plain data;
  supporting another model means adding a getter tuple and table rows.
