# Home Assistant validation plan — 0.3.0

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
   or camera reboots as part of sensor acceptance. This release has no setters.

## Rollback

Restore the previous integration directory and restart HA. The account-enabled
entry retains the old local credential fields, so the previous integration can
read it. Restore saved config-entry data only if necessary, with HA stopped;
restoring an old cloud token does not undo vendor-side token rotation and may
require a fresh email login when upgrading again.
