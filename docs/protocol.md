# SYR Connect polling protocol

How the LEXplus10S (firmware SLPS 2.0) talks to `syrconnect.de`, and how SYR
Local answers. Sources: our own capture (see [research.md](research.md)) and the
syrlex2mqtt protocol notes.

## Transport

- TLS 1.2 on port 443, **no SNI**, RSA key exchange (captured: `AES256-SHA`).
- The softener accepted a certificate signed by a private CA (mitmproxy) during
  the capture. It does not validate against public roots or pin SYR's
  certificate. SYR Local therefore uses its own CA, generated on first start.
- `User-Agent: LEXPlus Client`, `Accept-Language: pl`.
- The XML prolog claims utf-8, but text from this Polish firmware has been seen
  in iso-8859-2. SYR Local decodes UTF-8 when the bytes are valid UTF-8, and
  iso-8859-2 otherwise (after percent-decoding the `xml=` form field).

## Requests from the softener

| Request | Host | Body | SYR Local response |
| --- | --- | --- | --- |
| `POST /WebServices/SyrConnectLimexWebService.asmx/GetBasicCommands` | `syrconnect.de` | empty | `getSRN getVER getFIR getTYP getCNA`, all `v=""` |
| `POST /WebServices/SyrConnectLimexWebService.asmx/GetAllCommands` | `syrconnect.de` | form field `xml=` with the values asked for last time | the full read-only catalog at most once per `poll_interval`, otherwise an empty `<d></d>` |
| `POST /GetBasicCommands` | `maintenance.syrconnect.de` | malformed XML (`getMAC`, `getMAN`, `getDEN`, `getSTA`, `getDAT`) | **404** (any host starting with `maintenance.`) |
| `GET /firmware/saocal2/scf.cfg` | `firmware.syrconnect.de` | none | **404**, always (every GET is 404) |
| anything else | any | any | 404 |

The softener connects about every 11 s (basic + all), and tries `maintenance.`
about every 14 s.

## Message format

Both directions use the same shape:

```xml
<?xml version="1.0" encoding="utf-8"?>
<sc version="1.0"><d>
  <c n="getSRN" v="204033438" />
  <c n="getCNA" v="LEXplus10S" />
</d></sc>
```

- The server's response is a **list of commands the softener executes**. A
  `getXXX` with `v=""` asks for a value; a `setXXX` with a value changes the
  device (regeneration, salt amount, schedule, valve on SL models).
- The softener returns the requested values in its **next** request.
- Device bodies contain literal `\r\n` (backslash, r, backslash, n) between
  elements, and the maintenance body escapes quotes as `\"`. A strict XML
  parser fails, so SYR Local uses a tolerant regex:
  `<c\s+n=\\?"(name)\\?"\s+v=\\?"(value)\\?"`.
- Values are HTML-unescaped (`&amp;`, `&quot;`, numeric references). Custom
  entities are never expanded because nothing is parsed as XML.

## Read-only guarantees in SYR Local

| Guarantee | Implementation |
| --- | --- |
| Only `^get[A-Z0-9]{2,4}$`, always `v=""` | `catalog.ensure_read_only`, enforced in `protocol.build_response` for every response. A violation raises and the request gets a 500 with no commands. |
| Never `getSIR` | `catalog.FORBIDDEN`; SIR is the regeneration trigger (`setSIR 0` starts a regeneration). Reading it has no value. |
| Never `set*` | Rejected by the pattern; covered by tests |
| Never answer `scf.cfg` | All GETs are 404; there is no proxy and no outbound connection to SYR |
| Input bounds | 64 KB body (declared `Content-Length`; chunked bodies refused), ≤512 commands, values ≤512 chars (longer ones dropped), only getter names from the catalog are stored (so the in-memory map stays bounded), control characters stripped |
| Source restriction | Optional `allowed_device_ips` (IPs or CIDR networks; invalid entries stop the add-on) |

## Getter catalog (LEXplus10S)

`server/catalog.py::FULL_GETTERS`, 59 getters:

```
getSRN getVER getFIR getTYP getCNA getALM getCDE getCS1 getCS2 getCS3 getCYN
getCYT getDEN getDGW getDWF getFCO getFLO getINR getIPA getIWH getLAR getMAC
getMAN getNOR getNOT getOWH getPRS getPST getRDO getRES getRG1 getRG2 getRG3
getRPD getRPW getRTH getRTI getRTM getSCR getSRE getSS1 getSS2 getSS3 getSTA
getSV1 getSV2 getSV3 getTOR getVS1 getVS2 getVS3 getWHU getTOF getYEF getCWF
getLWF getCMF getLMF getCOF
```

This is the list the SYR cloud used (per syrlex2mqtt), without `getSIR`, plus
the consumption statistics. Which of them this unit actually answers is not
yet confirmed. Once real traffic has been seen, the list can be trimmed.

## Getter meanings used by SYR Local

| Getter | Meaning | Unit / format | Semantic key |
| --- | --- | --- | --- |
| `getSRN` | serial number | text | `device.serial` |
| `getCNA` | model name | `LEXplus10S` | `device.model` |
| `getMAN` | manufacturer | `Syr` | `device.manufacturer` (normalized to `SYR`) |
| `getFIR` / `getVER` | firmware name / version | `SLPS` / `2.0` | `device.firmware` = `SLPS 2.0` |
| `getTYP` | device type | `80` | `device.type` |
| `getMAC` | MAC address | `0C:73:EB:50:CE:C9` | `device.mac` (lower case) |
| `getIPA` | IP address | dotted quad | `device.ip` (falls back to the request source IP) |
| `getSS1` | salt lasts for | weeks | `salt_weeks` |
| `getSV1` | salt stored | kg | `salt_kg` |
| `getFLO` | current flow | **L/h (assumed)** | `flow_lph` |
| `getRES` | remaining softening capacity | L | `remaining_capacity_l` |
| `getCOF` | cumulative water consumption | L | `total_water_l` |
| `getRG1` | regeneration running | `0`/`1` | `regeneration_running` |
| `getCS1` | remaining resin capacity | % | `resin_percent` |
| `getPRS` | water pressure | 1/10 bar, `255` = invalid | `pressure_bar` |
| `getLAR` | last regeneration | epoch seconds of local wall time, `0` = never | `last_regeneration` (UTC ISO-8601) |
| `getTOR` | total regenerations | count | `regeneration_count` |
| `getSTA` | status message | text, empty = none | `status` |
| `getALM` | alarm code | text, empty = none | `alarm` |

`getDGW` is the default gateway, **not** water hardness (hardness is
`getIWH`/`getOWH`). All other getters stay in the internal raw map
(debug-logged), and are not exposed.
