# Motorola Nursery for Home Assistant

[![Validate](https://github.com/eduardobittencourt/motorola-nursery-ha/actions/workflows/validate.yml/badge.svg)](https://github.com/eduardobittencourt/motorola-nursery-ha/actions/workflows/validate.yml)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=eduardobittencourt&repository=motorola-nursery-ha&category=integration)

Community Home Assistant integration for Motorola Nursery cameras that use the
5GenCare MagicP2P tunnel. It provides local video plus optional cloud-backed
telemetry, controls, and detection events. Tested with one VM65CONNECT.

Version 0.5.0 also provides **sensors, controls and real-time detection events
through the Motorola cloud**.
Video and audio still travel over the LAN; telemetry requires internet access
and an account-linked entry. A telemetry outage does not interrupt local video.

## Sensors and camera information

On the verified VM65CONNECT, the integration discovers 18 additional entities:

- Temperature in °C and Wi-Fi signal quality in percent.
- Configured video bitrate, image brightness and night-vision mode.
- Speaker volume and motion/sound sensitivity settings.
- Low/high temperature thresholds and whether each temperature alert is enabled.
- Image inversion, motion-zone mode and the four zone enable states.

Hardware and firmware versions appear in the existing device information.
The sensor entities above remain read-only mirrors; version 0.4.0 adds separate
control entities for writable settings. Motion and sound sensitivity are
configuration values, not detection events. Zone enable states do not mean
motion was detected. The configured bitrate is not a measurement of current
network throughput.

The sensors share one poll every 60 seconds, use the camera credentials already
stored in the entry and do not rotate the account session. The client validates
TLS certificates and sends only allowlisted protocol commands. It does not read
Wi-Fi names, MAC addresses or sharing information.

Only advertised, supported capabilities become entities. Invalid individual
values become unavailable. If the cloud is unavailable at startup, the camera
still loads and sensors appear when telemetry recovers. Existing manual-only
entries retain local playback; use **Reconfigure > Connect or sign in to the
Motorola account** to enable sensor discovery.

## Controls

The verified VM65CONNECT controls include:

- Night vision (off, on or automatic), 50/60 Hz anti-flicker mode and four video
  quality levels: 160, 480, 640 and 1000 kbit/s.
- Brightness, speaker volume, motion/sound sensitivity and low/high temperature
  thresholds.
- Image inversion, low/high temperature alerts, motion-zone mode and each of the
  four zone enable states.
- Short-step pan/tilt buttons and return to origin. Every directional command
  sends a stop after 0.4 seconds, including when the operation is cancelled.
- A lullaby media player with 20 camera-advertised built-in tracks, volume and
  stop controls. Selecting a source starts playback on the camera speaker.

Controls are exposed only for fields advertised by the camera, except PTZ, which
is limited to VM65 models whose command set was physically validated. Every
setting write is read back before HA updates its state.

Firmware updates, reset/reboot, debug shell access, storage formatting, song
upload/removal and arbitrary protocol commands are deliberately blocked. The
microSD fields used by the app returned no data on the verified camera. Talkback
is not yet integrated. See
[PROTOCOL.md](PROTOCOL.md) for protocol details and compatibility limits.

## Motion and sound detections

An account-linked camera exposes two binary sensors and two native event
entities for real motion and sound detections. Binary sensors turn on for ten
seconds and include a `last_detected` timestamp. Native event entities emit a
`detected` event for every notification, including repeated detections within
those ten seconds.

The integration also fires `motorola_nursery_event` on the Home Assistant event
bus with `event_type` equal to `motion` or `sound`. The payload contains no media
filename, URL, account token or camera token. Home Assistant automations can use
the binary sensors, native event entities or the bus event to send a mobile
notification. The integration itself does not choose a notification recipient.

Detections use one persistent certificate-verified connection and normally
arrive without waiting for the 60-second telemetry poll. The listener answers
camera keepalives, reconnects with bounded backoff and deduplicates replayed
notifications. Detection entities become unavailable while this cloud channel
is disconnected; local video remains independent.

## Installation

Requires Home Assistant 2026.9.3 or newer.

Until the repository is included in the default HACS catalog, add it as a
custom repository:

1. Open HACS, choose **Custom repositories**, and enter
   `https://github.com/eduardobittencourt/motorola-nursery-ha` as an
   **Integration**.
2. Download **Motorola Nursery** and restart Home Assistant.
3. Open **Settings > Devices & services > Add integration**.

For manual installation, copy `custom_components/motorola_nursery` into the
Home Assistant configuration directory and restart Home Assistant.

## Account setup

1. Open **Settings > Devices & services > Add integration > Motorola Nursery**.
2. Enter the email used in Motorola Nursery, then the six-digit email code.
3. Select your camera and enter its local IP address or hostname.

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

## Support and security

Before opening a bug report, review the compatibility limits above and enable
debug logging only for the shortest time needed. Remove account identifiers,
camera addresses, stream URLs, email codes, tokens, and credentials from logs.
Use the repository's issue forms for reproducible bugs and feature requests.

Do not report vulnerabilities in a public issue. Follow
[SECURITY.md](SECURITY.md) to send a private report. Contributions are welcome;
see [CONTRIBUTING.md](CONTRIBUTING.md) and the
[Code of Conduct](CODE_OF_CONDUCT.md).

This independent interoperability project is not affiliated with Motorola,
5GenCare or Binatone. No APK, vendor library, packet capture or personal account
credentials are included. The VM65's shared RTSP application constants are
included solely to construct its local stream credentials.

Motorola and the Motorola logo are trademarks of Motorola Trademark Holdings,
LLC. Brand artwork is used only to identify compatible products; see
[BRAND_ASSETS.md](BRAND_ASSETS.md).
