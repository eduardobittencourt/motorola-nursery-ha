# Changelog

## 0.3.0 — 2026-09-27

- Add capability-based discovery of 18 read-only sensors/configuration states on
  VM65CONNECT, plus hardware/firmware information on the existing camera device.
- Poll the certificate-verified Motorola telemetry service once per minute
  without rotating account tokens or changing camera settings.
- Keep local video available during cloud telemetry failures; recover sensor
  discovery after startup outages and cancel polling on unload.
- Add protocol framing, invalid-value, TLS, no-write and HA lifecycle tests.
- Document the cloud dependency separately from the local video transport.

## 0.2.0 — 2026-09-25

- Add email-code login, camera selection and host setup in the Home Assistant UI.
- Add reauthentication and on-demand cloud credential renewal.
- Preserve existing manual configurations and RTSP overrides during migration.
- Add privacy-safe diagnostics and English and Brazilian Portuguese translations.
- Fix integration reload while camera streams are active.

## 0.1.0 — 2026-09-22

- Add the local MagicP2P-to-RTSP bridge and Home Assistant camera entity.
- Add on-demand H.264/AAC FFmpeg relay for native snapshots and HLS playback.
