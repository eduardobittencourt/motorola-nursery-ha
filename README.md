# Motorola Nursery Local for Home Assistant

Experimental Home Assistant integration for local video from Motorola Nursery
cameras that use the 5GenCare MagicP2P tunnel.

The integration opens an authenticated connection to TCP port 77 on the camera,
requests its internal RTSP service on port 6667, and exposes that stream only on
a dynamic loopback port inside Home Assistant. Home Assistant's `stream`
integration then provides snapshots and HLS playback.

## Current status

- Proven with one Motorola VM65 and one firmware/app combination.
- H.264 video and PCMA audio pass through without media transcoding.
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
VM65 TCP/77 -> MagicP2P tunnel -> loopback RTSP bridge -> HA camera/stream
```

Every RTSP client gets its own camera tunnel and cipher state. The listener is
bound to `127.0.0.1`, so it is not exposed to the LAN. No APK, vendor library,
packet capture, account credential, or device credential is included here.

## Roadmap

1. Validate reconnects, token lifetime, and additional devices.
2. Replace technical credential entry with account login/device selection or a
   safe import flow.
3. Add diagnostics with strict secret redaction and config-entry reauthentication.
4. Add full Home Assistant test coverage and HACS metadata.

This project is an independent interoperability effort and is not affiliated
with Motorola, 5GenCare, or Binatone.

