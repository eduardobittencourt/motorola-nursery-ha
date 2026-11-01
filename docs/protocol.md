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

The camera exposes local video separately from its outgoing data connection:

| Path | Connection | Purpose |
| --- | --- | --- |
| Local video | Camera TCP 77, tunneled to internal RTSP 6667 | Snapshots and HLS playback. |
| Account access | Certificate-verified TLS on vendor TCP 3388 | Email-code login, session resumption and device listing. |
| Incoming LAN data (opt-in) | Camera outgoing TCP 2278 redirected to the HA listener | Local telemetry and detection notifications. |
| Camera data (default) | Certificate-verified TLS on the account's routed `*.moto.5gencare.com` server, TCP 2288 | Telemetry, settings, controls and detection events. |

### Local video

The MagicP2P handshake requests an internal target port and authenticates with
an SID derived from the saved camera credentials. A successful handshake is
followed by the stateful byte transform implemented by `MagicCipher`; send and
receive maintain separate cipher states. Each chunk is transformed in an
executor worker, with a lock per direction to preserve ordering. Cancellation
closes the tunnel and waits for the transform before releasing its state.

The local acknowledgement is the ten-byte `ok 0 dconn` prefix, compared
case-insensitively as in the Android 2.2.18 native LAN path. It does not require
an echoed SID. This permits a camera to wait for the first RTSP request after
sending only that prefix. VM65 firmware also sends a space, the 78-byte SID and
one delimiter (LF, CR, NUL or space); the receive path strips that optional
suffix before decoding the stream, including when it is fragmented or arrives
with the first encrypted bytes. Bytes that do not match the optional echo are
preserved as cipher input, including a cipher prefix beginning with a space.
A matching echo with an invalid delimiter or truncated by EOF fails on receive.
The first receive has a separate eight-second deadline covering the optional
echo and initial cipher prefix through the first decoded data. Expiry closes
the tunnel, allowing the bridge to release its slot. Sending RTSP never waits
for the echo; subsequent receives have no initial-response deadline.

Local debug diagnostics distinguish credential validation, TCP connect,
handshake send, handshake receive and handshake validation, with an overall
eight-second connection deadline. The initial acknowledgement read is bounded
to ten bytes and leaves subsequent bytes for the receive path. Logs expose only
counts and allowlisted prefix/shape categories. `Local tunnel acknowledgement
suffix` distinguishes `sid_echo` from `none` when stream data arrives. Logs never
include raw bytes, SID, tokens, endpoints or exception text. A successful
acknowledgement alone does not prove working RTSP; a VM85CONNECT owner separately
confirmed setup and live video on firmware V1.6.45 / HA 2026.10.4 in
[issue #18](https://github.com/eduardobittencourt/motorola-nursery-ha/issues/18#issuecomment-6452538946).

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
an unsigned 32-bit owner ID, a 3–27-byte token and a 3–30-byte SID device value.
Cloud parsing and tunnel validation share the SID bounds; an unsupported row
rejects the list rather than silently dropping a camera or truncating credentials.

Version 0.5.5 accepts the 30-byte SID device value observed on VM85CONNECT.
The native Android 2.2.18 v1 implementation uses 20 as a minimum padding width,
not a maximum identifier size. Its SID output matches the existing algorithm
with the full 30-byte value; synthetic native reference vectors cover both
20 and 30 bytes. The accepted maximum of 30 is a supported-input bound, not a
claimed vendor protocol maximum. No credentials are truncated and the v1
SID generation and cipher are unchanged. Version 0.5.6 also accepts the short
local acknowledgement described above. The owner confirmed VM85 account setup
and live video; temperature and motion appeared correct in an initial check.
VM85 writable controls, PTZ, audio and prolonged operation remain unverified.

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
also describes motorised pan and digital tilt. This does not validate the
corresponding protocol commands. Buttons require individual writable
capabilities; logging a known model family does not enable them.

Complementary public research in
[Paradox101/motorola-babycam-ha-bridge](https://github.com/Paradox101/motorola-babycam-ha-bridge/blob/main/research/docs/magic-web2-protocol.md)
documents the vendor's WEB2 relay path and a VM65 capture. It is a useful protocol
reference; this integration uses the local LAN path and does not implement that
relay transport. The short local ACK handling was checked against the Android
2.2.18 native LAN implementation and then confirmed by the VM85 owner test.

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
other fields support controls/playback. The access marker is retained and
checked before writes. `existsongs`, `pan`, `tilt` and `ptz` are retained as
known command metadata when advertised, but never included in getter batches.
Capability metadata is cached
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

The numeric/boolean writes below were exercised on VM65CONNECT V1.6.37 and
restored to their initial values. Bounds and write access come from live
capability metadata, and each setting is verified by a subsequent getter.
This verifies configuration persistence; it does not independently establish
the efficacy of alert thresholds, sensitivities or spatial detection zones.

- `video_brightness`, `speaker_volume`, `motion`, `sound`,
  `temperature_low` and `temperature_high` are writable numeric settings.
- `night_vision`, `video_bitrate` and `video_light_frequency` are enumerated
  settings. Bitrate levels 0, 1, 2 and 3 yielded 160, 480, 640 and 1000 kbit/s.
- `ceiling_mount`, both temperature-alert switches, the motion-zone master and
  the four individual zone switches accept 0/1.
- PTZ is conditional on writable `pan`, `tilt` and `ptz` capabilities for each
  respective control. Directional commands require the requested direction to be
  acknowledged, with a stop attempted even on failure/cancellation. Origin must
  explicitly acknowledge `origin`. The tested VM65CONNECT advertises none of
  these capabilities: directions returned `stop`, origin returned `0`, and
  before/after images showed no change of framing. Earlier protocol ACKs were
  incorrectly treated as proof of physical PTZ support.
- `set existsongs 1` returned 20 built-in MP3 names. Playback uses
  `set playing <name>` and stopping uses `set audio_control 0`; state is exposed
  by `playing` and `audio_control`. Discovery runs in a separate background
  task, retries after failures on every successful poll (including unchanged
  readings), and is cancelled on unload. The unadvertised/unacknowledged
  `audio_timer` command is no longer sent.

The advertised microSD getter returned no storage fields on this camera, so
storage status and formatting are not integrated. Firmware updates, reset,
reboot, shell access, song upload/removal and talkback are deliberately excluded.

## Local telemetry investigation

Read-only probes on 2026-10-09 used one VM65CONNECT, hardware V1.2.03,
firmware V1.6.37. Those initial probes did not establish a local telemetry or detection-event
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
bridge. The default transport still uses the cloud channel; the incoming LAN
transport below provides a separate camera-initiated path. No camera settings were written during those probes, and
internet access was not blocked, so they do not establish offline telemetry.

## Failure and privacy boundaries

Cloud telemetry reads have a 15-second overall deadline, a 64 KiB line limit,
validated counts, duplicate-key rejection and bounded unrelated-message handling. An invalid
individual value is unavailable; malformed/incomplete responses fail the poll.
Telemetry connection errors never reset the camera, reload the integration or
invoke account renewal. The next scheduled poll retries with current saved credentials.

TLS verification is mandatory for account and cloud control connections. Exceptions and diagnostics omit raw messages,
credentials, account identifiers and camera/network addresses. Diagnostics expose
only setup/availability flags, the number of recognized capabilities, and local
connection/process counts.

A reported setting is not proof of physical actuation. Motion and sound notify
frames are implemented from the verified vendor protocol; physical detection
latency, long-term cloud behavior and other firmware versions need broader live
validation.
The local video path remains independent of this telemetry channel.

## Incoming LAN transport

`f3.py` implements the camera-initiated FePe V3 connection on TCP 2278;
`local.py` authenticates registrations and multiplexes property replies,
keepalives and detection notifications. A shared listener matches the saved
owner ID and per-camera Magic token. Network redirection is configured outside
the integration. The listener is not an HTTP endpoint or an RTSP proxy.

The 72-byte greeting contains a 16-byte version header, an ephemeral X25519
public key and a 24-byte nonce. Its fixed mask is the first 72 bytes of the
Blowfish P-array, a public format constant. A NaCl Box authenticates the random
1024-byte rolling table. Subsequent bytes use the directional rolling transform;
this legacy wire format does not authenticate each command. Restrict access to
the trusted camera network.

Initialization sends a generated UTC registration clock in BusyBox date format
and the saved device identifier in both MagicP2P setup fields. Session keys are
fresh per socket. Account passwords, active account sessions and captured cloud
bootstrap messages are not needed for polling. The listener never opens a
vendor connection. Getter responses use the same bounded allowlisted parsers
as the cloud client. A disconnect invalidates availability and the capability
cache is refreshed on a new connection; pending commands fail without fallback.
The F3 handshake has a 10-second deadline, followed by a separate 30-second
registration/setup deadline. Registration and MagicP2P setup are sent together.
The listener waits for a successful setup acknowledgement before exposing the
connection to getters; keepalives and notifications are dispatched while waiting.
A poll waits up to 20 seconds for a ready camera, then has a separate 40-second
deadline for capability discovery and value reads.

Camera-originated detection notifications can contain an additional fifth
opaque metadata field, observed on VM65CONNECT V1.6.37 for `sounddetect2`.
The local listener accepts a bounded 1–1024-character hint, validates the saved
camera token, acknowledges the frame and normalizes it to the four-field
app-facing notification parser. Event identity uses the type and opaque event
name; the hint is neither exposed nor retained. Invalid identities, overlong
hints and extra fields are rejected. Cloud event framing is unchanged.

Live validation on VM65CONNECT V1.6.37 read all 24 supported fields with the
camera WAN blocked, repeated a read after 60 seconds, and read again after
closing and re-establishing the camera socket. Initialization used only saved
setup credentials, without a cloud session or captured bootstrap. Transient
connection timeouts required retries; this is an experimental transport.
The installed candidate on Home Assistant 2026.10.4 also passed polling and
integration reload with the camera WAN blocked, preserving its entity IDs.

Readings and notification dispatch also have synthetic invalid-identity,
fragmentation, cancellation and reconnect coverage. Physical motion and sound
stimuli produced HA detections in both cloud and corrected LAN modes on
VM65CONNECT V1.6.37. Motion arrived during a WAN block with the local connection
and getters still healthy. Sound arrived shortly after that block expired, so
that trial does not establish offline sound detection or explain the camera's
alert cadence. Full camera boot with WAN already blocked and prolonged operation
remain unverified.
The LAN client now shares the cloud client's allowlisted control and playlist
implementation over the authenticated, serialized incoming session. Reconnection
invalidates both capability and playlist caches. All sixteen non-audio settings
passed live LAN write/readback and restoration through Home Assistant services.
Inversion, brightness and night vision also had visible effects in camera images.
The camera owner confirmed playback from the LAN playlist. A follow-up HA test
started/stopped white noise and exercised speaker levels 2 and 3. The microphone
AC signal rose during the higher-volume sample and returned to background after
stop and HLS buffer drainage; ambient sound was not controlled and this is not
an acoustic calibration. A physical hand movement produced native motion/sound
events and ten-second binary-sensor pulses. Anti-flicker efficacy, thermal alert
firing, sensitivity-response calibration and spatial zone exclusion remain
unverified. Actual PTZ on models advertising those controls has synthetic
coverage, without a physical motor test. Playlist discovery does not play audio.

A fully consumed but unusable playlist response leaves the shared LAN peer
connected, so readings and detection events continue while playlist loading
retries. Transport, framing and synchronization errors still close the peer
to prevent a later response from being mistaken for a new request.
