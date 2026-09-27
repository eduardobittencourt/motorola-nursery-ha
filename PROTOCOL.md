# Verified VM65CONNECT telemetry

The runtime client is independently implemented in `telemetry.py`. This document
records interoperability facts, not vendor code. No APK, native library,
decompiled source, private capture, device identifier or credential is included.

## Transport and authentication

The app's camera-control channel uses certificate-verified TLS on port 2288 of
the account's routed `*.moto.5gencare.com` server. This is separate from account
login on port 3388 and local MagicP2P video on camera port 77/internal port 6667.
No working local telemetry endpoint has been verified. In particular, the Hubble
HTTP getter path did not return telemetry on this VM65.

Messages are ASCII lines terminated with LF. TCP may split or combine lines.
Authenticate with `app <owner-id> <camera-magic-token>`; the observed acceptance
is `app 1 OK`. These are saved per-camera credentials, not a new account login.
The client does not call `v3_session` or rotate account tokens to poll sensors.
Keepalives use `ping`/`pong`; the app also acknowledges `pong` with `pang`.

`caplist` returns `caplist <count>` followed by five fields per capability:
name, access marker, type, minimum, maximum. The `w` marker means a setting is
writable by the vendor protocol; it can still be queried with a getter. Writes
use `set <name> <value>` and require an echoed response plus a matching readback.

`get <count> <name> ...` returns `get <count> <name> <value> ...`. A complete,
matching response is required. Only an explicit allowlist of 24 fields is read;
18 become telemetry entities, two update device metadata, and three describe
control/playback state. Capability metadata is cached
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

## Failure and privacy boundaries

Reads have a 15-second overall deadline, a 64 KiB line limit, validated counts,
duplicate-key rejection and bounded unrelated-message handling. An invalid
individual value is unavailable; malformed/incomplete responses fail the poll.
Connection errors never reset the camera, reload the integration or invoke
account renewal. The next scheduled poll retries with current saved credentials.

TLS verification is mandatory. Exceptions and diagnostics omit raw messages,
credentials, account identifiers and camera/network addresses. Diagnostics expose
only setup/availability flags and the number of recognized capabilities.

A reported setting is not proof of physical actuation. Event notifications,
long-term cloud behavior and other firmware versions need separate validation.
The local video path remains independent of this telemetry channel.
