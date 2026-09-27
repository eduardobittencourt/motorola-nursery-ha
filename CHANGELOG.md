# Changelog

## 0.5.0 — 2026-09-27

- Add real-time motion and sound detection over the camera's authenticated,
  certificate-verified push channel.
- Add pulse-style binary sensors and native Home Assistant event entities so
  closely spaced detections remain individually usable in automations.
- Fire privacy-minimized `motorola_nursery_event` bus events containing only the
  configured device identifier, detection type and receive timestamp.
- Reconnect with bounded backoff, answer protocol keepalives and deduplicate
  replayed vendor notifications without interrupting local video or telemetry.
- Add parser, authentication, keepalive, privacy and deduplication tests.
- Harden optimized-runtime error handling and document the protocol-mandated
  non-security SHA-1 identifier explicitly for static analysis.
- Add security reporting, contribution guidelines, issue/PR templates,
  dependency updates, pinned CI actions, Bandit, coverage gating and CodeQL.

## 0.4.0 — 2026-09-27

- Add validated controls for night vision, image settings, quality, alert
  thresholds, sensitivities, alert switches and motion-zone enable states.
- Add short-step pan/tilt buttons with an unconditional stop and a return-to-origin
  button for the verified VM65CONNECT command set.
- Add a camera-side lullaby player with its 20 dynamically discovered built-in
  tracks, stop control and normalized speaker volume.
- Confirm quality levels as 160, 480, 640 and 1000 kbit/s and keep the diagnostic
  bitrate sensor synchronized immediately after changes.
- Strictly allowlist writable fields, values, playlist names and PTZ commands;
  firmware, reset, debug shell, storage formatting and song mutation remain blocked.
- Add synthetic protocol and full Home Assistant service lifecycle tests.

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
