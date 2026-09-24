# Motorola Nursery Local for Home Assistant

Experimental Home Assistant integration for local video from Motorola Nursery
cameras that use the 5GenCare MagicP2P tunnel.

The integration opens an authenticated connection to TCP port 77 on the camera,
requests its internal RTSP service on port 6667, and exposes that stream only on
a dynamic loopback port inside Home Assistant. An on-demand FFmpeg relay copies
the H.264 video and converts the camera's PCMA audio to AAC. Home Assistant's
native `stream` integration then provides snapshots and HLS playback.

## Current status

- Proven with one Motorola VM65 and one firmware/app combination.
- Native HLS validated at 1920x1080 with H.264 video and AAC-LC mono audio.
- Video is copied without re-encoding; only PCMA audio is converted to AAC.
- No custom WebRTC integration is required for snapshot or HLS playback.
- The technical device credentials must currently be imported manually.
- Token refresh, cloud-independent startup, discovery, and other camera models
  have not been validated.
- The existing standalone bridge remains the production path while this custom
  integration is evaluated side by side.

## Development install

Copy `custom_components/motorola_nursery` to the Home Assistant configuration
directory, restart Home Assistant, and add **Motorola Nursery Local** from
Settings > Devices & services. The first development version asks for the raw
technical parameters. Do not share them or include them in bug reports.

## Architecture

```text
VM65 TCP/77 -> MagicP2P -> loopback RTSP -> FFmpeg H.264/AAC -> HA Stream/HLS
```

Every RTSP client gets its own camera tunnel and cipher state. Both listeners
are bound to `127.0.0.1`, so neither is exposed to the LAN. FFmpeg starts only
while Home Assistant consumes the source and is terminated on disconnect or
config-entry unload. No APK, vendor library, packet capture, account credential,
or device credential is included here.

## Roadmap

1. Validate reconnects, token lifetime, and additional devices.
2. Replace technical credential entry with account login/device selection or a
   safe import flow.
3. Add diagnostics with strict secret redaction and config-entry reauthentication.
4. Add full Home Assistant test coverage and HACS metadata.

This project is an independent interoperability effort and is not affiliated
with Motorola, 5GenCare, or Binatone.
