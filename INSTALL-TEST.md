# Home Assistant validation plan — 0.5.0

The package contains only custom_components/motorola_nursery. No account
configuration, capture or research tooling is included.

## Before installing

1. Back up the current custom_components/motorola_nursery directory.
2. Back up the existing Motorola config-entry data securely, and record the
   entry/entity identifiers. Do not publish the config-entry backup.
3. Replace the integration files, run HA configuration validation, then restart
   Home Assistant. This interrupts other integrations briefly.

## Live acceptance

1. Confirm the existing camera entity still provides a snapshot and playback.
2. On an account-linked VM65CONNECT, confirm 18 additional sensor/binary-sensor
   entities attach to the existing device, with firmware/hardware information.
3. Compare temperature with the monitor/app. It uses tenths of °C on the wire;
   threshold settings use whole °C. Confirm Wi-Fi is a percentage, not dBm.
4. Confirm values refresh after at least one 60-second polling interval and
   the original camera entity still provides a snapshot and HLS playback.
5. Test cloud failure/recovery synthetically. Do not disable the home's internet
   or camera connection while monitoring a baby. Legacy manual entries must
   retain video without attempting cloud telemetry; link the account only when
   sensor onboarding is explicitly being tested.
6. Check sanitized diagnostics and logs. Do not force token expiry or alter the
   working account just to exercise an artificial failure.
7. Do not test audio playback, talkback, PTZ, night-vision writes, firmware updates
   or camera reboots as part of unattended sensor acceptance.

## Control acceptance while the camera is free

1. Change each number/select/switch once and restore its original value. Confirm
   the read-only diagnostic entity follows the write on the next poll.
2. Press each directional PTZ button and confirm movement stops automatically;
   press Return to origin at the end.
3. Lower lullaby volume, select one built-in source, confirm playing state, stop,
   and restore the original volume.
4. Confirm snapshot and HLS after controls. Do not exercise firmware, reset,
   storage formatting, debug shell, song upload/removal or arbitrary commands.

## Detection acceptance

1. Confirm motion/sound binary sensors and event entities are attached to the
   existing camera device and are available.
2. Move through the camera image. Confirm the motion binary sensor pulses for ten
   seconds and the motion event entity records a `detected` event.
3. After any camera-side cooldown, clap near the camera. Confirm the equivalent
   sound entities update. Do not use the camera's own PTZ or speaker as stimuli;
   this firmware suppresses those self-generated changes.
4. Listen for `motorola_nursery_event` and verify its payload contains only
   `device_id`, `event_type` and `detected_at`.
5. Confirm snapshot, HLS and telemetry remain available throughout the test.

## Rollback

Restore the previous integration directory and restart HA. The account-enabled
entry retains the old local credential fields, so the previous integration can
read it. Restore saved config-entry data only if necessary, with HA stopped;
restoring an old cloud token does not undo vendor-side token rotation and may
require a fresh email login when upgrading again.
