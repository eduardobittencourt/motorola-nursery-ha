# Motorola Nursery protocol

[Documentation index](README.md) · [Development and maintenance](development.md)

This reference records interoperability facts and their compatibility limits.
The independent implementation lives in
[`protocol.py`](../custom_components/motorola_nursery/protocol.py) (local tunnel),
[`cloud.py`](../custom_components/motorola_nursery/cloud.py) (account access),
[`telemetry.py`](../custom_components/motorola_nursery/telemetry.py) (settings and
controls) and [`events.py`](../custom_components/motorola_nursery/events.py)
(detection notifications). No APK, native library, decompiled source, private
capture, device identifier or credential is included.

## Transports

The camera exposes local video separately from the cloud services used by the
integration:

| Path | Connection | Purpose |
| --- | --- | --- |
| Local video | Camera TCP 77, tunneled to internal RTSP 6667 | Snapshots and HLS playback. |
| Account access | Certificate-verified TLS on vendor TCP 3388 | Email-code login, session resumption and device listing. |
| Camera data | Certificate-verified TLS on the account's routed `*.moto.5gencare.com` server, TCP 2288 | Telemetry, settings, controls and detection events. |

### Local video

The MagicP2P handshake requests an internal target port and authenticates with
an SID derived from the saved camera credentials. A successful handshake is
followed by the stateful byte transform implemented by `MagicCipher`; send and
receive maintain separate cipher states. Each chunk is transformed in an
executor worker, with a lock per direction to preserve ordering. Cancellation
closes the tunnel and waits for the transform before releasing its state.

The integration uses internal RTSP port 6667. A loopback-only RTSP bridge feeds
an on-demand FFmpeg relay, which copies H.264 video and converts PCMA audio to
AAC for Home Assistant's native Stream integration. Both listeners bind to
`127.0.0.1` on ephemeral ports. The relay's HTTP path contains a random token.
See [development and maintenance](development.md#development-setup) for module
responsibilities.

## Account access

The account client uses certificate-verified TLS on port 3388, initially at
`9.moto.5gencare.com`. It handles newline-framed ASCII messages and idle
`ping`/`pong`, including while the user enters the email code.

- `v3_otp`: submit a fresh 32-character uppercase alphanumeric client identity,
  email address and six-digit code length; obtain user ID and routing host.
  A two-field `-6 <vendor-host>` reply redirects this request: reconnect with
  verified TLS and repeat the same identity/email, with at most two redirects
  and no repeated hosts. Other negative replies remain errors.
- `v3_loginset`: submit that identity, email and received code; obtain a session.
- `v3_session`: resume with user ID, token and session ID. The replacement token
  must be saved before any subsequent network operation, including device listing.
- `v3_dlist`: retrieve a count followed by seven fields per device, including
  tunnel credentials and a URL-encoded display name.

HA writes config-entry storage asynchronously. A sudden process or power loss
during session rotation can require reauthentication. The local access token is
SHA-1 of the camera magic token concatenated with the VM65 application's shared
RTSP password, as required by the vendor protocol. Imported RTSP overrides are
preserved; unused login and device fields are not interpreted.

## Device-list diagnostics and model limits

The supported `v3_dlist` layout is one count (0–32), followed by seven fields
per camera: owner ID, device identifier, model, encoded name, MagicP2P token,
SID device value and an unused trailing field. The current local tunnel needs
an unsigned 32-bit owner ID, a 3–27-byte token and a 3–20-byte SID device value.
These limits are preserved when collecting diagnostics; an unsupported row
rejects the list rather than silently dropping a camera or truncating credentials.

Debug logs describe declared/expected/received field counts, zero-based record
index, field lengths and kinds (`empty`, `decimal`, `negative_decimal`, `text`),
credential validation flags and failed rule names. `model_family` is restricted
to known VM65/VM85 names or `other`; it never echoes an arbitrary model field.
The cloud wire format is ASCII, so logged field lengths also describe byte
lengths. Raw field values, IDs, names and tokens are omitted. Malformed camera
details produce a camera-response UI error, distinct from network failures.

The manufacturer's [VM85CONNECT support page](https://motorolanursery.com/support/product-support/?productId=5637)
and [EU/US user guide](https://www.motorolanursery.com/media/yjoliuma/vm85-connect-ug-en-eu-us-v3.pdf)
confirm Motorola Nursery app support. The public product documentation reviewed
does not specify `v3_dlist`, tunnel credential sizes or local RTSP endpoints.
Using the same app does not prove matching camera firmware or tunnel behavior.
The [VM85 product page](https://www.motorolanursery.com/nursery-care-products/connected-video-baby-monitors/vm85-connect)
also describes motorised pan and digital tilt, so VM65 physical PTZ validation
must not be applied to VM85. VM85 remains physically unverified; logging its
known family is diagnostic classification, not an enablement of model controls.

## Camera telemetry and events

Messages are ASCII lines terminated with LF. TCP may split or combine lines.
Authenticate with `app <owner-id> <camera-magic-token>`; the observed acceptance
is `app 1 OK`. These are saved per-camera credentials, not a new account login.
The client does not call `v3_session` or rotate account tokens to poll sensors.
Keepalives use `ping`/`pong`; the app also acknowledges `pong` with `pang`.

The camera broadcasts detection notifications on the same authenticated
connection as `notify <camera-magic-token> <type> <opaque-event-name>`. Verified
types are `motiondetect`, `sounddetect` and `sounddetect2`. The integration
validates the token and exact frame shape, maps both sound variants to one sound
event, and never stores or exposes the opaque event name. A bounded in-memory
fingerprint cache suppresses replayed notifications after reconnects.
Connection setup and authentication share a 15-second deadline. Reconnect delay
increases from one to at most 60 seconds and resets after authentication.

`caplist` returns `caplist <count>` followed by five fields per capability:
name, access marker, type, minimum, maximum. The `w` marker means a setting is
writable by the vendor protocol; it can still be queried with a getter. Writes
use `set <name> <value>` and require an echoed response plus a matching readback.

`get <count> <name> ...` returns `get <count> <name> <value> ...`. A complete,
matching response is required. Only an explicit allowlist of 24 fields is read;
telemetry fields become entities, version fields update device metadata, and
other fields support controls/playback. Capability metadata is cached
after a successful read, rediscovered after a protocol/transport error, and reset
when the integration reloads. Each poll opens and closes one TLS connection.

## Verified values

Validated on one VM65CONNECT, hardware V1.2.03, firmware V1.6.37. This firmware
advertises 43 capabilities; that does not establish support on other models.

| Field | Interpretation |
| --- | --- |
| `temperature_reading` | Signed integer in tenths of °C; divide by 10. Advertised range −200…500. |
| `wifi_signal` | Quality percentage, 0…100; not RSSI/dBm. |
| `videoKbps` | Configured video bitrate, kbit/s. |
| `night_vision` | **0 off, 1 on, 2 automatic**. This differs from Hubble mappings. |
| `video_brightness` | Brightness setting, 0…4. |
| `speaker_volume` | Speaker setting, 1…6; reading it does not play audio. |
| `motion`, `sound` | Sensitivity settings, 0…4 and 0…5 respectively; not event detections. |
| `temperature_low`, `temperature_high` | Alert thresholds in whole °C, unlike the temperature measurement. |
| `lowtemp_switch`, `hightemp_switch` | Whether each temperature alert is enabled, 0/1. |
| `ceiling_mount` | Image inversion setting, 0/1; not a motor control. |
| `video[0].motion_zone` | Motion-zone mode enabled, 0/1. |
| `video[0].motion.zone[0..3].enable` | Individual zone enable state, 0/1. |
| `hardware_version`, `firmware_version` | Version strings, displayed in device information. |

The temperature scale was confirmed against the app's conversion and a nearby
monitor reading. The protocol client was validated with all 24 allowlisted
values in one request.

## Verified controls

All writes below were exercised on the camera and, where applicable, restored to
their initial values. Numeric and enumerated settings are bounded by the live
capability metadata before transmission and verified by a subsequent getter.

- `video_brightness`, `speaker_volume`, `motion`, `sound`,
  `temperature_low` and `temperature_high` are writable numeric settings.
- `night_vision`, `video_bitrate` and `video_light_frequency` are enumerated
  settings. Bitrate levels 0, 1, 2 and 3 yielded 160, 480, 640 and 1000 kbit/s.
- `ceiling_mount`, both temperature-alert switches, the motion-zone master and
  the four individual zone switches accept 0/1.
- PTZ uses `set pan left|right`, `set tilt up|down` and a matching `stop`. The
  integration sends a short pulse and guarantees a stop attempt. Recenter uses
  `set ptz origin`.
- `set existsongs 1` returned 20 built-in MP3 names. Playback uses
  `set playing <name>` and stopping uses `set audio_control 0`; state is exposed
  by `playing` and `audio_control`. The app also sends `set audio_timer 120`, but
  this firmware does not acknowledge that command.

The advertised microSD getter returned no storage fields on this camera, so
storage status and formatting are not integrated. Firmware updates, reset,
reboot, shell access, song upload/removal and talkback are deliberately excluded.

## Local telemetry investigation

Read-only probes on 2026-10-09 used one VM65CONNECT, hardware V1.2.03,
firmware V1.6.37. They did not establish a local telemetry or detection-event
API:

- Authenticated RTSP `GET_PARAMETER` requests for `temperature_reading` and
  `wifi_signal` returned 200 with an empty body.
- An HTTP service on internal port 9090 responded through MagicP2P. Tested
  getter paths, including the Hubble-style temperature getter, returned 404 or
  timed out. No working telemetry response was obtained.
- A successful `ok 0 dconn` handshake could be followed by reset or EOF. Tunnel
  authentication alone does not establish that an internal service is usable.

These observations apply to the tested requests and firmware; they do not
exclude other local APIs. Port 9090 is not exposed by the integration's RTSP
bridge. The integration continues to use the cloud channel for telemetry and
notifications. No camera settings were written during those probes, and
internet access was not blocked, so they do not establish offline telemetry.

## Failure and privacy boundaries

Telemetry reads have a 15-second overall deadline, a 64 KiB line limit,
validated counts, duplicate-key rejection and bounded unrelated-message handling. An invalid
individual value is unavailable; malformed/incomplete responses fail the poll.
Telemetry connection errors never reset the camera, reload the integration or
invoke account renewal. The next scheduled poll retries with current saved credentials.

TLS verification is mandatory. Exceptions and diagnostics omit raw messages,
credentials, account identifiers and camera/network addresses. Diagnostics expose
only setup/availability flags, the number of recognized capabilities, and local
connection/process counts.

A reported setting is not proof of physical actuation. Motion and sound notify
frames are implemented from the verified vendor protocol; physical detection
latency, long-term cloud behavior and other firmware versions need broader live
validation.
The local video path remains independent of this telemetry channel.
