# Compatibility

[Documentation index](../README.md)

## Tested models

| Model | Firmware | Confirmed scope |
| --- | --- | --- |
| PIP1610HDCONNECT, hardware V1.0 | V1.2.15 | Email-code login, local snapshot/HLS with H.264/AAC, temperature/Wi-Fi readings, motion/sound events, advertised settings, lullaby playback/volume and directional pan/tilt controls. |
| VM65CONNECT, hardware V1.2.03 | V1.6.37 | Email-code login, local snapshot/HLS with H.264/AAC, temperature/Wi-Fi readings, motion/sound events, advertised settings and LAN lullaby playback/volume. |
| VM85CONNECT | V1.6.45 | Owner-reported account setup, local connection and live video. Temperature and motion had an initial check; audio, writable controls and prolonged use were not separately validated. |

The VM85CONNECT result was reported with Home Assistant 2026.10.4 and
integration candidate 0.5.6b2; see the
[owner confirmation in issue #18](https://github.com/eduardobittencourt/motorola-nursery-ha/issues/18#issuecomment-6452538946).

These observations describe particular units, not every firmware or region.
Synthetic protocol tests do not establish additional retail-model compatibility.

## Feature limits

Entities depend on advertised capabilities and usable values. A model name does
not enable PTZ. VM65CONNECT does not advertise the required axes; PIP1610HDCONNECT
exposes directional `pan` and `tilt` controls and an integer `ptz` capability.
Talkback is not integrated.
Anti-flicker effectiveness, thermal alarm firing, sensitivity calibration and
spatial-zone exclusion are not established by successful setting writes.

## Network and account limits

Beta [local QR pairing](local-pairing.md) has been physically validated on one
VM65CONNECT with fresh HA-generated credentials, local readings and H.264/AAC.
A camera cold boot with WAN blocked also recovered when the network supplied a
local response to its public-IP connectivity probe. This remains a routing-assisted
result, not a guarantee of offline startup on an ordinary network.

Successful offline startup does not guarantee recovery after reloading the
integration. Incoming control reconnection remains experimental; video may
continue while readings are unavailable.

On an ordinary LAN without the routing workaround, WAN loss can interrupt
locally paired VM65CONNECT readings while video and audio continue initially.
A cold boot can leave video unavailable until external connectivity returns.
Local QR pairing does not guarantee continuous offline readings or startup.

Local video requires camera TCP port 77 and a manually supplied reachable
address. Address discovery is not implemented. Default telemetry and detections
use the cloud independently of video.

Experimental incoming LAN readings support the same allowlisted controls and
lullabies, with router configuration. WAN-blocked readings and motion have been
exercised on an already initialized VM65CONNECT. This does not establish
independent startup or network recovery. The tested firmware can repeat DHCP
discovery when external reachability probes fail, interrupting local media even
though the LAN remains available. Its initialization also uses external services
beyond the incoming LAN connection.

Experimental network emulation has recovered local video, audio and readings
after offline startup, but the integration does not provide or manage those
additional services. A supported standalone replacement and prolonged offline
reliability are not established. These observations do not establish the
behavior of other models or firmware.

Offline cold boot is not guaranteed, and a static DNS override has not been
demonstrated as a workaround. The incoming LAN redirect covers the readings and
control connection, not every service the camera may need during startup or
recovery. Offline sound and prolonged offline operation remain unverified.
Local mode has no automatic account renewal or cloud fallback.

Recovery after real credential changes, long-term expiry, account sharing,
concurrent phone sessions, multiple HA instances and other regions remain
unverified. Recovery checks the tunnel handshake; rejection by internal RTSP
alone is not a renewal trigger.

## Reports

Include model, firmware, HA/integration version, transport and the features
actually tested in a compatibility issue. Separate video, audio, readings,
controls and sustained operation. Never attach tokens, serials or private media.
