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
- generated HLS: valid playlist and 60 decoded H.264 frames at 1920x1080;
- entry survives a full Home Assistant restart.

The HLS provider did not include the camera's PCMA track. The registered WebRTC
provider advertises support for the entity and may transcode audio for browser
playback, but that path needs an automated media assertion before it is marked
validated. The standalone production path continues to use go2rtc to produce
AAC audio.

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
