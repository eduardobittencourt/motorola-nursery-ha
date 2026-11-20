# Incoming LAN readings (experimental)

[Documentation index](../README.md)

This guide covers cameras paired through the Motorola account. Cameras paired
with the beta [local QR flow](local-pairing.md) already target HA directly and do
not require the control-port redirect below.

After account setup, open **Reconfigure > Use local entity readings** and enable the
local transport. This requires network configuration: redirect only the camera's
outgoing TCP port **2278** to the Home Assistant host on TCP **2278**, and allow
its return traffic. The integration cannot install router rules. Ordinary access
to the camera's IP address is insufficient because the camera initiates this
connection. Both directions must pass through the redirecting gateway; a
separate HA return route may require source NAT for this connection. Keep the
listener private to your camera network.

This mode polls the same supported values every 60 seconds and receives detection
notifications over the authenticated camera connection. Existing entity IDs are
preserved. It reconnects using the credentials saved during account setup and
has no cloud fallback. Camera reset or account relinking can change those
credentials and require manual account setup again.

Local transport does not guarantee that the camera can start or recover without
internet access. The integration does not replace all camera initialization
services; see the tested [startup limits](compatibility.md#network-and-account-limits)
before relying on it during an outage. A DNS override alone is not a validated
workaround.

This mode supports readings, detection events and the same allowlisted setting
and lullaby commands as the cloud transport. Playlist discovery runs separately
from readings and retries after failures. Local video continues using the
camera's TCP port 77. LAN playback and volume were exercised on VM65CONNECT;
physical PTZ on models advertising those axes remains unverified.

See [architecture](../reference/architecture.md) for transport ownership and
[compatibility](compatibility.md) for model-specific limits.
