# Development status

## Reliability candidate (0.5.1)

The expanded synthetic suite passes 54 tests with 88% line coverage on both
Home Assistant 2026.9.3 and 2026.10.1. It covers active forwarding failures,
camera EOF versus viewer disconnects, bounded event reconnects, authentication
deadlines and cancellation of slow telemetry/playlist requests during unload.

On the target HA 2026.10.1, an isolated HA process using the real VM65CONNECT
loaded the candidate in about 0.2 seconds, read 24 telemetry fields and connected
the event channel. Telemetry and events recovered after entry reload; unload
left no relay process or bridge connection, with no integration errors. Account
renewal and control actions were disabled in this acceptance process, and the
production config entry data remained unchanged.

The candidate relay delivered real MPEG-TS data. Native snapshot/HLS acceptance
in the auxiliary process did not complete: the stream worker encountered I/O
failures and camera resets while the primary instance remained active. The cause
is not established. The primary instance returned HTTP 200 with a valid JPEG.
The candidate has not been activated in the primary instance; full media
acceptance there and live credential recovery remain pending.

An auxiliary HA process inside HAOS must use a separate config directory and
remove every `SUPERVISOR*` and `HASSIO*` environment variable before loading HA,
including `SUPERVISOR_CORE_API_SOCKET`. Load only the required integrations and
verify that `hassio` is absent. Otherwise the auxiliary instance can publish its
own API port to the real Supervisor and trigger a watchdog restart of primary HA.

## Validated controls (0.4.0)

Live reversible tests confirmed every advertised numeric/boolean setting on the
VM65CONNECT. PTZ left/right/up/down, stop and origin were physically exercised.
The camera returned 20 built-in lullaby filenames; playback, state reporting,
stop and volume restoration were confirmed. Quality levels map to 160, 480, 640
and 1000 kbit/s. The app's microSD getter returned only supported audio fields,
so storage entities are intentionally omitted.

The write client allowlists fields, checks camera-advertised bounds, requires the
echoed write and reads settings back. PTZ has a bounded duration and unconditional
stop. Playlist filenames and selections are validated. The test suite covers HA
number/select/switch/button/media-player services without contacting the camera.

Version 0.4.0 was then installed on the target Home Assistant after a successful
configuration check and a component/config-entry backup. After restart, all 42
registered entities shared the original device: the camera, 18 telemetry mirrors
and 23 controls. Representative number, select, switch, PTZ and lullaby services
were exercised through the HA API and their original values restored. The entry
remained loaded, all telemetry was available, JPEG snapshot and HLS media returned
HTTP 200, and the logs contained no Motorola integration error.

## Read-only telemetry (0.3.0)

See [PROTOCOL.md](PROTOCOL.md) for the independently implemented TLS telemetry
protocol and verified VM65CONNECT fields. The telemetry test suite uses synthetic
responses and the real HA entity lifecycle. It covers delayed discovery after an
initial cloud failure, sensor unavailability/recovery without stopping video,
shared device identity, metadata and polling cleanup. Media dependencies are
mocked in the lifecycle test; it does not contact a camera or cloud service.

Live validation on Home Assistant 2026.9.3 found 18 available telemetry entities
and the original camera on one device, with hardware V1.2.03 and firmware V1.6.37.
Configuration validation passed. After installing 0.3.0 and restarting HA,
snapshot and HLS media requests returned HTTP 200. All 40 automated tests and
Ruff checks pass. Automatic one-minute polling remained healthy for more than
40 minutes after deployment, and the HA logs contained no integration errors.
No camera-setting commands were sent. Multi-day telemetry availability and
other devices remain unverified.

## Scope of validation

The original manual-credential integration was validated on Home Assistant
2026.9.3 with a VM65: local tunnel, JPEG snapshot, H.264/AAC HLS and restart.
The email-code protocol was separately verified using a fresh client identity,
without reusing a captured login token.

Version 0.2.0 adds native email/code forms, camera selection, host entry,
reconfiguration, reauthentication and on-demand credential recovery. Automated
tests use the real Home Assistant config-entry and flow infrastructure with
synthetic cloud/camera responses. Version 0.2.0 was validated as 0.2.0-dev.2 on
the target HA. Configuration validation passed, the existing entry and camera
entity survived restart, snapshot and HLS returned HTTP 200, and the
reconfiguration email form opened successfully.
The final release also fixes shutdown order for active clients and cancels
forwarding tasks on tunnel teardown. Live reload during HLS playback completed
in 0.61 seconds and the snapshot worked again afterward. All 21 tests pass.
Email-code login through the HA UI was completed successfully. The account
session is stored, the same entry remains loaded, and snapshot/HLS returned
HTTP 200 again after account linking.

## Reproducible tests

Use Python 3.14 and a virtual environment:

The pinned Home Assistant test plugin currently selects Home Assistant
2026.10.1 and compatible versions of pytest, pytest-asyncio and coverage. Those
packages are intentionally not pinned a second time in `requirements-test.txt`.
The integration's minimum supported Home Assistant remains 2026.9.3.
CI tests both environments. The minimum job fixes test plugin 0.13.366, which
selects HA 2026.9.3; the current job follows `requirements-test.txt`. Both share
`requirements-test-tools.txt`. Update the minimum job only when intentionally
raising the integration's documented minimum HA version.

```sh
python3.14 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
.venv/bin/ruff check custom_components tests
.venv/bin/ruff format --check custom_components tests
.venv/bin/bandit -q -r custom_components/motorola_nursery
.venv/bin/coverage run --source=custom_components/motorola_nursery -m pytest -q
.venv/bin/coverage report --fail-under=80
```

Tests do not send email or contact vendor servers. Protocol and relay tests
open loopback listeners with generated data. Tests cover framing and keepalive,
login/retry/abort, legacy reconfiguration, session rotation before list failure,
serialized refresh, local playback without cloud, and diagnostic redaction.

## Observed authentication protocol

The client opens certificate-verified TLS to the vendor's camera service on
port 3388, initially `9.moto.5gencare.com`. It handles newline-framed ASCII
messages, including fragmented/coalesced reads and idle ping/pong.

- `v3_otp`: submit a fresh 32-character uppercase alphanumeric client identity,
  email address and six-digit code length; obtain user ID and routing host.
- `v3_loginset`: submit that identity, email and received code; obtain session.
- `v3_session`: resume using user ID, token and session ID. The returned token
  replaces the previous token, which was observed to stop working.
- `v3_dlist`: retrieve a count followed by seven fields per device, including
  tunnel credentials and a URL-encoded display name.

The local access token is SHA-1 of the device magic token concatenated with the
VM65 application's shared RTSP password. Imported RTSP overrides are preserved.
The unused login response field and unknown device fields are not interpreted.

Save rotated tokens before any subsequent network operation. HA's normal
config-entry storage writes asynchronously, so sudden process/power loss during
rotation may require reauthentication. Do not log wire messages, stream URLs,
session tokens, codes or device credentials.

## Remaining validation

- Observe long-term session lifetime, rejected-session repair and phone coexistence.
- Validate recovery under real credential changes, not only synthetic failures.
- Test other models, regions and multiple cameras/accounts.
- Add network discovery and validate additional camera models and regions.

No APK, proprietary shared library, packet capture, firmware image or personal
credential belongs in this repository.
