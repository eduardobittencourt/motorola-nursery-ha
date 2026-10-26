# Changelog

## Unreleased

- Organize protocol, development/validation and brand documentation under
  `docs/`, with an index and updated links from the README and contributor guide.
- Preserve the local telemetry investigation's results and limits in the protocol
  reference, replacing the link to a private research path with a public summary.
- Update the HACS badge and installation guidance to reflect inclusion in the
  default catalog, and remove outdated version announcements from the README.
- Document HACS distribution and release maintenance for contributors.

## 0.5.1 — 2026-10-20

- Transform camera stream chunks in executor workers instead of blocking the
  event loop, keeping cipher state and transport operations ordered per direction.
- Lead installation instructions with searching for Motorola Nursery in HACS.
- Recover from camera tunnel errors and EOF during an active video stream while
  keeping ordinary local viewer disconnects quiet.
- Reset event reconnection backoff after authentication and bound connection
  setup and authentication with a shared deadline.
- Load initial telemetry and lullaby playlists in the background so cloud
  delays do not hold up local camera startup; cancel pending work on unload.
- Add privacy-safe event connection and video process counters to diagnostics.
- Cover transport failures, reconnects, slow cloud requests and cancellation;
  run CI against both minimum-supported and current Home Assistant versions.
- Update compatible test dependencies and CodeQL together, and prevent
  conflicting dependency pins and separate CodeQL action updates.
- Consolidate contributor/testing guidance and remove development-session diaries
  from the maintained documentation.

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
