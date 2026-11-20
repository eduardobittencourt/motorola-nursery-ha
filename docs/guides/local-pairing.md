# Local QR pairing (beta)

[Documentation index](../README.md)

Version 0.9.0b6 adds an experimental **Pair locally with HA** setup path for
**VM65CONNECT**. Home Assistant generates the Wi-Fi QR and camera credentials,
serves enrollment during a ten-minute window, and provides the runtime clock, selector HTTP-DNS and
incoming local control. No add-on, Motorola app or account is used by this path.
Local enrollment, fresh-credential media and incoming readings have been
physically validated on one VM65CONNECT. This beta still requires supervised
setup; other models, firmware versions and prolonged offline use remain unverified.

Choose **Pair locally with HA (beta)** or **Motorola account** when adding the
integration. These are separate setup modes. Changing modes requires pairing the
camera again using the chosen method and creating a new HA config entry; there
is no automatic conversion of an existing entry. Entity identities and history
are not guaranteed to carry over when replacing an entry. Updating the integration
within the same mode keeps the existing entry and identities.

## Before pairing

- Use a private 2.4 GHz Wi-Fi network and a DHCP reservation for the camera.
  Automatic camera address discovery is not implemented.
- Give HA a stable private IPv4 LAN address. Permit the camera to reach HA on
  TCP **3378** (only while pairing), **4400** (clock), **40280** (SDK HTTP-DNS) and **2278** (control).
  HA must reach the camera on TCP **77** for video.
- Configure your LAN DNS for the selector that the camera constructs. If the
  HA address is `192.168.1.10`, both `192.168.1.10.5gencare.com` and
  `192.168.1.10.5gencare.com.lan` must resolve directly to `192.168.1.10`.
  Use your own HA address in all three positions. These are exact LAN DNS
  overrides, not public DNS records or broad vendor-domain overrides.
- Do not expose these listeners to the internet. Pair only on a trusted network.
  Enrollment is restricted to the supplied camera address and a random identifier
  carried by the QR; the legacy request does not provide a modern device identity
  proof. Protect the QR and do not share screenshots.

Locally paired cameras connect directly to HA on TCP2278. A router control-port
redirect is not required when the selector DNS and ordinary LAN routing are
correct. This differs from the account-paired [incoming LAN mode](local-readings.md).

The SDK may also query public HTTP-DNS resolver addresses on TCP40280. The beta
serves only the configured HA selector on that port, accepting registered camera
source addresses. Reaching this local responder instead of a public resolver
requires external network routing or interception; ordinary DNS overrides alone
do not redirect requests sent to an IP address. Preserve the camera source
address when forwarding these requests to HA. This is not an open DNS resolver
or a cloud proxy.

The integration does not configure your router, DNS or firewall. Local QR pairing
does not guarantee offline readings or cold startup, even with the HA listeners
and selector DNS available. Firmware may
also test connectivity by pinging a hardcoded public IP. A local response or
working WAN may still be needed for startup. Installing an add-on alone would
not remove this routing requirement. See [compatibility](compatibility.md#network-and-account-limits).

## Configure in Home Assistant

1. Open **Settings → Devices & services → Add integration → Motorola Nursery**.
2. Choose **Pair locally with HA (beta)**.
3. Enter the Wi-Fi name and password, reserved camera address and HA LAN address.
   This beta accepts SSIDs of 1–32 UTF-8 bytes and passwords of 8–63 UTF-8 bytes.
4. Switch HA to a light theme so the QR is black on white. Inverted codes from
   a dark theme may not be recognized by the camera. Once the QR appears, use
   the camera's physical pairing button as described by
   its manufacturer, then show the QR to the lens. The integration does not send
   reset or firmware commands.
5. Wait for **pairing success**, then submit. HA verifies the incoming control
   connection and local video before creating the entry. If not ready, wait and
   submit again. After a video failure, you may explicitly choose **Save pairing
   and continue investigating video** to retain the authenticated camera keys;
   this does not mean playback has recovered. A cancelled or expired flow closes
   the enrollment listeners;
   start a new attempt to generate a new QR.

Wi-Fi credentials and the QR remain only in the active configuration flow and
are discarded on completion, cancellation or expiry. Generated camera credentials
are stored in the HA config entry. Do not delete the entry unless you intend to
pair again; it contains the local credentials. A local entry uses no cloud
fallback or automatic Motorola credential renewal. Its **Reconfigure** menu lets
you change the reserved camera address or start **Change Wi-Fi**. The clock and HTTP-DNS listeners are shared across
locally paired entries and close after the last entry or pairing flow releases them.

## Change Wi-Fi without replacing the entry

For an existing locally paired camera, open its **Reconfigure → Change Wi-Fi**
menu. Enter the new SSID/password, the address reserved for the camera on the
new network, and the HA LAN address. Keep the same HA-targeting DNS records
accessible on the new network. Generate the QR only when you can show it to the
camera; the enrollment window is ten minutes.

The QR reuses the existing owner, device ID and camera keys. The current control
registration remains available while the flow is open; it is not registered a
second time. HA verifies control from the candidate address and probes its local
video before updating this same entry. Names, credentials and entity IDs remain
unchanged. For a move to a different address, HA can also finish when the camera
reconnects with its existing keys without a new enrollment acknowledgement. This
requires a new control session from that address and successful video authentication;
the old session cannot confirm the move. A same-address move still requires the
normal enrollment acknowledgement. You may submit to verify connectivity after a
camera failure announcement; HA will not treat that announcement as proof of success.

Cancellation, expiry or failed verification leaves the saved entry
unchanged. If another configuration changes during the flow, start again.

The camera changes Wi-Fi only after you physically present the QR. Cancelling HA
after the camera has moved does not undo that physical change. Keep the old Wi-Fi
available until verification completes. If video alone fails after authenticated
control, the explicit save-pairing option can preserve the new address for further
diagnosis. A newly selected address must have a DHCP reservation; automatic address
discovery is not implemented.

This migration flow has synthetic lifecycle/identity tests. A migration between
physical Wi-Fi networks remains a separate device-owner validation step.

## Existing cameras and rollback

Pairing replaces the camera's previous association. An existing cloud entry is
not silently converted; use this flow only when you intend to pair the camera
again. Keep the stable HACS installation route; see [beta installation and
rollback](troubleshooting.md#testing-a-beta-release).

Returning to a stable version that predates local pairing also requires pairing
the camera through Motorola Nursery and creating or reconfiguring its account
entry. Reinstalling stable code alone cannot recover credentials replaced by a
new local pairing. Remove selector DNS overrides only after restoring the
camera's normal vendor selector or deliberately replacing the local service.
