# Motorola Nursery Local for Home Assistant

Experimental Home Assistant integration for local video from Motorola Nursery
cameras that use the 5GenCare MagicP2P tunnel. Tested with one VM65.

## Account setup (0.2.0-dev.2)

1. Copy `custom_components/motorola_nursery` into your Home Assistant configuration
   directory and restart Home Assistant.
2. Open **Settings > Devices & services > Add integration > Motorola Nursery Local**.
3. Enter the email used in Motorola Nursery, then the six-digit email code.
4. Select your camera and enter its local IP address or hostname.

The integration obtains the camera credentials and checks the local connection.
No packet capture, phone proxy, or manually copied token is needed.

For an existing installation, open the entry's **Reconfigure** menu and choose
account login. This preserves the entry and camera entity. Existing manually
configured entries continue working without account login. The same menu lets
you change the camera address.

Session and camera credentials are stored in Home Assistant's config entry;
the email code is not saved. Protect your HA configuration and backups as you
would other account credentials. Diagnostics omit account and device data.

## Playback and renewal

Video travels locally: TCP port 77 on the camera tunnels its internal RTSP
service on port 6667. Two private loopback listeners feed an on-demand FFmpeg
relay and Home Assistant's native Stream integration. H.264 video is copied;
PCMA audio is converted to AAC. No third-party WebRTC integration is required.

Startup uses saved camera credentials. If a local connection fails, an
account-connected entry attempts cloud credential renewal, with a cooldown
between attempts. Each successful session resumption rotates the cloud token;
the replacement is saved in the config entry before fetching devices.
A rejected session starts Home Assistant reauthentication. Sending another
email code always requires submitting the email form.

## Validation and limits

- The earlier manual integration produced 1920x1080 HLS with AAC mono audio
  and survived a Home Assistant restart.
- Independent email-code login, device retrieval, session rotation and local
  RTSP access were verified against one VM65 account outside Home Assistant.
- This account-enabled development version has automated tests against Home
  Assistant 2026.9.3. On the target HA, the existing camera survived the upgrade
  and restart. Email-code login through the HA UI succeeded, the session was
  saved, and snapshot/HLS returned HTTP 200 after account linking.
  Long-term credential recovery still requires live validation.
- Long-term session expiry, other regions/models, account sharing and concurrent
  phone sessions remain unverified. Camera address discovery is not implemented.
- Recovery checks the tunnel handshake; rejection by the camera's internal RTSP
  service alone is not currently a renewal trigger.

See [DEVELOPMENT.md](DEVELOPMENT.md) for testing and protocol details.

This independent interoperability project is not affiliated with Motorola,
5GenCare or Binatone. No APK, vendor library, packet capture or personal account
credentials are included. The VM65's shared RTSP application constants are
included solely to construct its local stream credentials.
