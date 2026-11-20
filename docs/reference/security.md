# Security boundaries

[Documentation index](../README.md)

Session and camera credentials are stored in the private HA config entry. Email
codes are not saved. Protect HA configuration and backups. Cloud TLS certificates
are verified; local camera protocol compatibility does not establish modern
end-to-end media encryption.

Internal media listeners use loopback. The optional incoming LAN listener uses
TCP 2278 and must remain private to the camera network. Limit router redirects
to the intended camera connection; do not publish this listener to the internet.
The initial NaCl Box authenticates the session rolling table, but the subsequent
legacy rolling transform does not authenticate each command. Session setup
therefore does not establish per-message integrity; restrict access to the
trusted camera network. See [protocol reference](protocol.md).

Only known, advertised and bounded controls are exposed. Firmware updates, reset,
formatting, shell access and arbitrary commands are blocked. Account renewal is
serialized and disabled in local-only readings mode. No telemetry outage should
trigger unrelated camera actions or break local video.

Logs and diagnostics omit account/device credentials, identifiers and private
addresses. Review excerpts before publication; other HA integrations can log
private data. Never attach raw captures, vendor binaries or private media.
Report vulnerabilities through [SECURITY.md](../../SECURITY.md).

The beta local pairing flow temporarily opens TCP3378, accepts only the supplied
camera source address, a fresh QR identifier and the supported model, and pins
subsequent requests to the first accepted device identifier. Enrollment expires
after ten minutes; a bounded TCP4400 clock accepts only registered camera source
addresses. TCP40280 HTTP-DNS accepts only registered camera sources and resolves
only the HA selector associated with that camera. It does not resolve other
hostnames, forward requests or contact upstream services. Requests are bounded,
body-free GETs; no received fields enter logs. All bootstrap services limit
concurrent connections, request time and framing.
The legacy enrollment request cannot cryptographically prove physical device
identity. The QR identifier/source restriction is a trusted-LAN boundary, not
modern device authentication. Do not enable pairing on an untrusted network.
Wi-Fi data is not persisted; only generated camera credentials enter HA storage.
