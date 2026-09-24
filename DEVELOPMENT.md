# Development status

## Live validation

The custom integration is installed as the sole VM65 camera path on a Home
Assistant 2026.9.3 system. The earlier standalone systemd bridge, Generic Camera
entry, dedicated go2rtc stream, test dashboard, captures, and research tooling
were removed after native validation.

Validated through the custom integration entry:

- config flow verifies a real MagicP2P handshake before creating the entry;
- the bridge binds to an ephemeral `127.0.0.1` port inside Home Assistant;
- the camera entity supplies an authenticated RTSP source to Home Assistant;
- generated snapshot: JPEG, 1920x1080, HTTP 200;
- generated HLS: H.264 Main video at 1920x1080 and AAC-LC mono audio at 16 kHz;
- entry survives a full Home Assistant restart.

The first native HLS validation did not include the camera's PCMA track because
Home Assistant Stream supports AAC and MP3 audio, not G.711/PCMA. The integration
now includes an on-demand, loopback-only FFmpeg relay. It copies H.264 without
re-encoding and converts only PCMA audio to AAC before Home Assistant consumes
the source. Native HLS was validated without the third-party WebRTC Camera custom
integration. Home Assistant's internal system provider may still offer WebRTC
as an additional frontend path, but this integration neither configures nor
requires it.

## Deliberately deferred

- account login and device selection;
- automatic token acquisition and refresh;
- network discovery and DHCP address changes;
- reauthentication and repairs;
- multiple firmware/model coverage;
- HACS release metadata and release automation;
- long-running and offline-start tests.

No proprietary APK, shared library, packet capture, firmware image, or secret
belongs in this repository. Protocol tests use generated fixtures only.
