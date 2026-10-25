# Installation

This guide assumes Home Assistant OS or Supervised (add-ons available), a
FritzBox router and AdGuard Home as DNS server, as in the reference setup.
Other routers and DNS servers work the same way.

**Never change anything on the softener itself.** No static IP or DNS on its
display, no app setting changes, no firmware changes. The redirect happens
entirely in DNS and is fully reversible.

## 1. Install the add-on

1. *Settings → Add-ons → Add-on store → ⋮ → Repositories*, add
   `https://github.com/valentinpurrucker/syr-local`.
   (Alternatively, copy the `syr_local/` folder to `/addons/syr_local` on the
   host; it then shows up under *Local add-ons*.)
2. Install **SYR Local** and start it. Check the log:
   ```
   SYR Local (read-only) listening: device TLS on 0.0.0.0:8443, state API on 0.0.0.0:8099
   Requesting 59 getters at most every 60 s; set* and getSIR are refused; ...
   ```
3. Optional: set `allowed_device_ips` to the softener's IP (for example
   `192.168.178.130`). This only works reliably if the softener keeps its IP;
   consider a DHCP reservation in the FritzBox (router side, not on the device).

### Port 443 conflict

The softener always connects to port 443. If the add-on fails to start with a
port error, another add-on already publishes host port 443 (typically NGINX
Proxy Manager or the NGINX SSL proxy). The softener sends no SNI, so an
SNI-based proxy cannot share the port. The Supervisor publishes add-on ports
on all host addresses, so a second IP address does not help either. Move the
other add-on to a different host port in its *Network* settings (for NGINX
Proxy Manager, for example, use 8443 and forward that port in the router
instead).

## 2. Install the integration

Either:

- **HACS:** *HACS → ⋮ → Custom repositories*, add the repository URL with type
  *Integration*, install **SYR Local**, restart Home Assistant; or
- **Manual:** copy `custom_components/syr_local` to
  `/config/custom_components/syr_local` and restart Home Assistant.

The integration needs Home Assistant 2026.10 or newer.

## 3. Redirect DNS

The softener resolves `syrconnect.de` (and `maintenance.syrconnect.de`,
`firmware.syrconnect.de`). Both changes below are needed. Without the FritzBox
exception the softener gets an empty DNS answer and goes offline altogether.

1. **AdGuard Home → Filters → DNS rewrites**, add two rules pointing at the IP
   address of your Home Assistant host:
   - `syrconnect.de` → `<HA IP>` (an apex rule is required; the wildcard does
     not match the apex in AdGuard)
   - `*.syrconnect.de` → `<HA IP>`
2. **FritzBox → Heimnetz → Netzwerk → Netzwerkeinstellungen →
   DNS-Rebind-Schutz → Hostnamen-Ausnahmen**, one per line, no wildcards:
   ```
   syrconnect.de
   maintenance.syrconnect.de
   firmware.syrconnect.de
   ```
   Click *Übernehmen*.
3. Wait up to ~5 minutes for the router's DNS cache, then check from a computer
   on the LAN:
   ```sh
   dig +short @<adguard-ip> syrconnect.de   # must print the HA IP
   dig +short @192.168.178.1 syrconnect.de  # router: must match; empty = rebind protection still active
   ```

Pi-hole: *Local DNS → DNS Records* for `syrconnect.de`,
`maintenance.syrconnect.de` and `firmware.syrconnect.de`, or a dnsmasq
`address=/syrconnect.de/<HA IP>` line (covers subdomains too).

## 4. Confirm

- Add-on log: `Device identified: serial 204033438, model LEXplus10S`, then
  `Discovery sent for …`.
- *Settings → Devices & services*: **SYR Local** appears under *Discovered*.
  Click *Add* and confirm.
- The device page shows salt, flow, capacity and consumption within about a
  minute (the add-on requests a full read at most once per `poll_interval`).
- An occasional `Refused GET /firmware/saocal2/scf.cfg … (404)` in the log is
  expected and is exactly what should happen.

If the add-on had already seen the softener before the integration was
installed, Home Assistant may not have had anywhere to send the discovery
message. Restart the add-on once; it re-announces the persisted serial. Manual
setup below always works as well.

### Manual setup (no discovery)

*Settings → Devices & services → Add integration → SYR Local*, then enter the
add-on's hostname (from the add-on's *Info* page, for example
`a1b2c3d4-syr-local`, or `local-syr-local` for a local add-on) and port `8099`.
The form reports `no_device` until the softener has contacted the add-on at
least once. To use the integration from a different Home Assistant instance,
publish port 8099 in the add-on's *Network* settings, but only on a trusted
network: the state API has no authentication.

## Rollback

1. Delete the two AdGuard rewrites (and optionally the FritzBox exceptions).
2. Within a few minutes (router DNS cache) the softener talks to the SYR cloud
   again. It retries every ~11 seconds, so nothing on the device needs a reset.
3. Stop or uninstall the add-on and remove the integration if desired.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Add-on log shows no requests | DNS not redirected for the router: check `dig @<router>`; rebind exception missing; router cache not expired yet |
| `Rejected request from … (not in allowed_device_ips)` | Softener IP changed; update the option or clear it |
| Integration says `no_device` | Add-on running but softener not seen yet |
| Entities unavailable | Softener not heard from for 5 minutes, or add-on stopped |
| Values missing, device known | The softener has not answered a full read yet; wait one `poll_interval` plus ~11 s |
| `unsupported_version` | Add-on and integration from different releases; update both |
