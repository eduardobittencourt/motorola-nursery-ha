# Motorola Nursery for Home Assistant

[![Validate](https://github.com/eduardobittencourt/motorola-nursery-ha/actions/workflows/validate.yml/badge.svg)](https://github.com/eduardobittencourt/motorola-nursery-ha/actions/workflows/validate.yml)
[![HACS](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=eduardobittencourt&repository=motorola-nursery-ha&category=integration)

Community Home Assistant integration for Motorola Nursery cameras that use the
5GenCare MagicP2P tunnel. It provides local video, telemetry and detection events,
with an optional incoming LAN transport for camera readings. Cloud transport
remains available for telemetry and controls. Local video is verified on VM65CONNECT
and confirmed by a VM85CONNECT owner. See [validation and limits](#validation-and-limits)
for the features tested on each model.

Video and audio travel over the LAN. Account access obtains credentials during
setup. The default telemetry transport uses the cloud; the incoming LAN mode
uses saved credentials without cloud connections or automatic renewal. A
telemetry outage does not interrupt local video.

## Sensors and camera information

The sensor entities expose temperature in °C and Wi-Fi signal quality in percent.
Hardware and firmware versions appear in the existing device information.
Configuration values are shown directly by their number, select and switch
entities; separate sensors no longer duplicate them. Motion and sound detection
binary sensors and event entities remain separate from sensitivity controls.

### Upgrading from duplicated setting sensors

The integration removes its 16 obsolete setting-mirror sensor/binary-sensor
registry entries automatically at setup. Existing control, measurement and
detection entity IDs remain unchanged; recorder/history data is not deleted.
Update references to the old mirrors before upgrading: use the corresponding
number, select or switch entity. In particular, configured bitrate is now shown
by the video-quality select (for example `640_kbit_s`) instead of the numeric
bitrate sensor. The local transport still reports control states even though
setting writes are not yet supported in that mode.

The sensors share one poll every 60 seconds, use the camera credentials already
stored in the entry and do not rotate the account session. The cloud client
validates TLS certificates; both transports send only allowlisted protocol
commands. Neither reads
Wi-Fi names, MAC addresses or sharing information.

Only advertised, supported capabilities become entities. Invalid individual
values become unavailable. Initial telemetry and playlist requests run in the
background so slow telemetry responses do not delay local camera startup.
Sensors appear when the selected telemetry transport becomes available. Existing manual-only
entries retain local playback; use **Reconfigure > Connect or sign in to the
Motorola account** to enable sensor discovery.

## Incoming LAN readings (experimental)

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

This first implementation provides readings and detection events. Setting writes,
PTZ and lullaby commands are unavailable in this mode; those commands have not
been validated over the incoming transport. The standard cloud mode retains its
existing controls. Local video continues using the camera's TCP port 77.

See [the protocol guide](docs/protocol.md#incoming-lan-transport) for connection
initialization and verification limits.

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
is not yet integrated. See the [protocol reference](docs/protocol.md) for
protocol details and compatibility limits.

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

In the default cloud mode, detections use one persistent certificate-verified
connection and normally arrive without waiting for the 60-second telemetry poll. The listener answers
camera keepalives, reconnects with bounded backoff and deduplicates replayed
notifications. Detection entities become unavailable while this cloud channel
is disconnected; local video remains independent.

## Installation

Requires Home Assistant 2026.9.3 or newer.

Motorola Nursery is included in the default HACS catalog; no custom repository
is needed. [Open Motorola Nursery in HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=eduardobittencourt&repository=motorola-nursery-ha&category=integration)
or follow these steps:

1. Open HACS and search for **Motorola Nursery**.
2. Download **Motorola Nursery** and restart Home Assistant.
3. Open **Settings > Devices & services > Add integration > Motorola Nursery**
   and follow the account setup below.

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

Startup uses saved camera credentials. In the default transport, if a local
video connection fails, an account-connected entry attempts cloud credential
renewal, with a cooldown
between attempts. Each successful session resumption rotates the cloud token;
the replacement is saved in the config entry before fetching devices.
A rejected session starts Home Assistant reauthentication. Sending another
email code always requires submitting the email form. Incoming LAN mode disables
automatic account renewal; credentials can be refreshed manually by account setup.

## Validation and limits

- Compatibility has been tested with one VM65CONNECT, hardware V1.2.03 and
  firmware V1.6.37. Local snapshot/HLS with H.264 video and AAC mono audio,
  email-code login, telemetry and controls have been verified on this model.
- The experimental incoming LAN transport read all 24 supported values on
  VM65CONNECT V1.6.37 with WAN blocked, including a 60-second polling interval
  and socket reconnection. Motion and sound notifications were also received
  after physical stimuli in LAN mode. Motion arrived during a camera WAN block;
  the offline sound trial was inconclusive. Reconnection can require retries;
  cold boot and prolonged operation still need validation.
- A VM85CONNECT owner confirmed account setup, local connection and live video
  on firmware V1.6.45 with Home Assistant 2026.10.4, using the 0.5.6b2 candidate
  promoted to this stable release. Temperature and motion appeared correct in
  the initial check; prolonged operation, audio and writable controls were not
  separately validated. See the [confirmation in issue #18](https://github.com/eduardobittencourt/motorola-nursery-ha/issues/18#issuecomment-6452538946).
- Automated tests use real Home Assistant lifecycle/config-flow infrastructure
  with synthetic camera/cloud responses. CI covers minimum-supported and current
  HA test environments; see [CONTRIBUTING.md](CONTRIBUTING.md).
- Recovery after real credential changes and concurrent streaming from multiple
  HA instances remain unverified.
- Long-term session expiry, other regions/models, account sharing and concurrent
  phone sessions remain unverified. Camera address discovery is not implemented.
- Recovery checks the tunnel handshake; rejection by the camera's internal RTSP
  service alone is not currently a renewal trigger.

See the [documentation index](docs/README.md) for protocol details,
development, testing and release maintenance. Contribution guidelines are in
[CONTRIBUTING.md](CONTRIBUTING.md).

## Support and security

For account login failures, follow the [troubleshooting guide](docs/troubleshooting.md)
to enable debug logging even when first setup cannot finish.

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
[brand assets](docs/brand-assets.md).
