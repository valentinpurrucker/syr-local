# State API (schema version 1)

The only interface between the add-on and the integration. It is served by the
add-on on port 8099, which is reachable on the internal Supervisor network and
not published to the host by default. There is no authentication; do not
publish the port to untrusted networks.

## Endpoints

| Method + path | Response |
| --- | --- |
| `GET /api/v1/state` | `200`, the state document below. Also `200` before any device contact. |
| `GET /health` | `200`, `{"status": "ok"}` (add-on watchdog) |
| anything else | `404`, `{"error": "not_found"}` |

## Document

```json
{
  "schema_version": 1,
  "generated_at": "2026-10-25T14:00:00+00:00",
  "device": {
    "serial": "204033438",
    "manufacturer": "SYR",
    "model": "LEXplus10S",
    "firmware": "SLPS 2.0",
    "type": "80",
    "mac": "0c:73:eb:50:ce:c9",
    "ip": "192.168.178.130"
  },
  "values": {
    "salt_weeks": 5,
    "salt_kg": 8.0,
    "flow_lph": 0.0,
    "remaining_capacity_l": 1215,
    "total_water_l": 583939,
    "regeneration_running": false,
    "resin_percent": 60,
    "pressure_bar": 4.8,
    "last_regeneration": "2026-01-02T03:45:17+00:00",
    "regeneration_count": 391,
    "status": null,
    "alarm": null
  },
  "meta": {
    "started_at": "2026-10-25T13:00:00+00:00",
    "last_seen": "2026-10-25T13:59:50+00:00",
    "last_read": "2026-10-25T13:59:00+00:00",
    "request_count": 42
  }
}
```

## Rules

- `schema_version`, `generated_at`, `device`, `values` and `meta` are always present.
- `device` always has all seven keys; unknown ones are `null`. After an add-on
  restart, `serial` and `model` come from the persisted identity until the
  softener reports again.
- `values` contains only keys that have a usable value. It is `{}` before the
  first full read. Readings are never persisted, so after a restart `values` is
  empty until the softener answers again.
- `status` and `alarm` are present with `null` when the softener reported an
  empty string (nothing to report), and absent when never reported.
- Numbers are JSON numbers, booleans are booleans, timestamps are ISO-8601 with
  a UTC offset.
- `meta.last_seen`: last accepted device request (any of the two endpoints).
  `meta.last_read`: last request that carried at least one semantic value.
  Both are `null` until the first contact. `meta.request_count` counts accepted
  device requests since the add-on started.

## Values

| Key | Type | Unit | Source |
| --- | --- | --- | --- |
| `salt_weeks` | integer | weeks | `getSS1` |
| `salt_kg` | number | kg | `getSV1` |
| `flow_lph` | number | L/h | `getFLO` (unit assumed, see research) |
| `remaining_capacity_l` | integer | L | `getRES` |
| `total_water_l` | integer | L | `getCOF` |
| `regeneration_running` | boolean | | `getRG1` (`1` = true) |
| `resin_percent` | integer | % | `getCS1` |
| `pressure_bar` | number | bar | `getPRS` / 10; omitted for `255` |
| `last_regeneration` | string | ISO-8601 UTC | `getLAR`, read as local wall time in the HA time zone (`TZ`); omitted for `0` |
| `regeneration_count` | integer | | `getTOR` |
| `status` | string or null | | `getSTA` |
| `alarm` | string or null | | `getALM` |

Negative, non-finite or unparseable numbers are omitted.

## Compatibility

- The integration rejects any `schema_version` other than `1`
  (`unsupported_version`), and payloads that break the rules above
  (`invalid_response`). If the document names a different serial number than
  the configured device, the integration marks its entities unavailable
  (`wrong_device`) instead of showing another softener's values.
- Unknown keys in `values` are ignored by the integration, so new values can be
  added without a version bump. Renaming or removing a key, or changing a
  type or unit, requires `schema_version: 2`.
- The keys are defined in `syr_local/server/mapping.py::VALUE_KEYS` and
  `custom_components/syr_local/models.py::VALUE_TYPES`;
  `tests/test_contract.py` keeps them in sync.
