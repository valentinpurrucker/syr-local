# SYR Local

A strictly read-only, local stand-in for `syrconnect.de` for the SYR LEXplus10S
Connect water softener. It makes the softener's data available to the **SYR
Local** integration without the SYR cloud.

## How it works

The softener contacts `syrconnect.de` over HTTPS about every 11 seconds and asks
for commands. Once your DNS sends those requests to this add-on, it answers with
read-only `get` commands only, at most once per poll interval. The softener
reports the values in its next request, and the add-on serves them to Home
Assistant.

The add-on never sends `set` commands and never sends `getSIR` (the regeneration
trigger). It never answers the firmware check and never contacts the SYR cloud.

## Setup

1. Start the add-on. On first start it creates a local CA and certificate
   under `/data/certs`; they are kept across restarts and updates.
2. Make sure nothing else on the host uses port 443 (see *Port 443* below).
3. Redirect `syrconnect.de` and `*.syrconnect.de` to the IP address of your Home
   Assistant host in your DNS server (AdGuard Home, Pi-hole or similar). On a
   FritzBox, also add the names as DNS rebind protection exceptions. See the
   repository's `docs/install.md` for step-by-step instructions.
4. Within about a minute the log shows `Device identified: serial …`, and Home
   Assistant offers the **SYR Local** integration under *Settings → Devices &
   services*.

## Options

| Option | Default | Description |
| --- | --- | --- |
| `poll_interval` | `60` | Minimum seconds between two full read requests (10–3600). |
| `allowed_device_ips` | `[]` | Only accept requests from these IPs or networks, for example `192.168.178.130`. Empty accepts any source. Invalid entries stop the add-on instead of silently allowing everything. |
| `log_level` | `info` | `debug`, `info`, `warning` or `error`. `debug` logs every request and the raw values. |
| `log_requests` | `false` | Write raw request bodies to `/data/requests.log` (rotated, about 3 MB at most). Contains the serial number and MAC address. |

## Network

| Container port | Host port | Purpose |
| --- | --- | --- |
| 8443/tcp | 443 | HTTPS endpoint the softener connects to |
| 8099/tcp | not published | State API for the integration. Discovery sends the add-on's internal hostname (shown on the add-on's *Info* page, for example `a1b2c3d4-syr-local`, or `local-syr-local` for a locally copied add-on). |

### Port 443

The softener always connects to port 443. If another add-on (for example
NGINX Proxy Manager) already publishes host port 443, the Supervisor cannot
start SYR Local. The softener sends no SNI, so an SNI-based proxy cannot share
the port either. Move the other service to a different host port (see
`docs/install.md` in the repository).

## Troubleshooting

- **No `Device identified` in the log.** Check that `syrconnect.de` resolves to
  the Home Assistant host from your router (`dig +short @<router-ip>
  syrconnect.de`). An empty answer usually means the router's DNS rebind
  protection is blocking it.
- **`Refused GET /firmware/saocal2/scf.cfg (404)`.** This is expected and safe:
  the softener checks for firmware now and then, and the add-on never answers.
- **Rollback.** Remove the DNS rewrites. The softener is back on the SYR cloud
  within minutes; nothing on the device needs to be reset.
