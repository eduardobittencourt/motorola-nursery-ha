# Development status

## Live validation

The initial custom integration was installed alongside the existing standalone
bridge on a Home Assistant 2026.9.3 test system. The existing systemd service,
Generic Camera entry, go2rtc stream, and dashboard were left in place.

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
the source. Native HLS was validated after disabling the third-party WebRTC
Camera config entry. Home Assistant's own system go2rtc provider may still offer
WebRTC as an additional frontend path, but the integration does not require it.
The standalone production path continues to use go2rtc as a fallback.

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
