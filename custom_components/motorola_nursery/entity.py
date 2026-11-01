"""Shared identity and availability for telemetry-backed entities."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .capabilities import setting_supported
from .const import DOMAIN
from .coordinator import MotorolaTelemetryCoordinator


class MotorolaCoordinatorEntity(CoordinatorEntity[MotorolaTelemetryCoordinator]):
    """Attach telemetry-backed entities to the existing camera device."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: MotorolaTelemetryCoordinator, entry: ConfigEntry, key: str
    ):
        super().__init__(coordinator)
        self._key = key
        identifier = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{identifier}:{key}"
        values = coordinator.data.values if coordinator.data else {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, identifier)},
            manufacturer="Motorola Nursery",
            model=entry.data.get("model", "VM65"),
            name=entry.title,
            sw_version=values.get("firmware_version"),
            hw_version=values.get("hardware_version"),
        )


class MotorolaTelemetryEntity(MotorolaCoordinatorEntity):
    """A coordinator entity backed by one telemetry value."""

    @property
    def available(self) -> bool:
        return super().available and self.value is not None

    @property
    def value(self) -> int | str | None:
        data = self.coordinator.data
        return data.values.get(self._key) if data else None


class MotorolaSettingEntity(MotorolaTelemetryEntity):
    """A writable setting remains usable only while its capability is present."""

    @property
    def available(self) -> bool:
        return super().available and setting_supported(self.coordinator.data, self._key)


# These configuration states are already exposed by number/select/switch entities.
SETTING_MIRRORS = {
    ("sensor", "videoKbps"): ("select", "video_bitrate"),
    ("sensor", "night_vision"): ("select", "night_vision"),
    **{
        ("sensor", key): ("number", key)
        for key in (
            "video_brightness",
            "speaker_volume",
            "motion",
            "sound",
            "temperature_low",
            "temperature_high",
        )
    },
    **{
        ("binary_sensor", key): ("switch", key)
        for key in (
            "ceiling_mount",
            "lowtemp_switch",
            "hightemp_switch",
            "video[0].motion_zone",
            *(f"video[0].motion.zone[{index}].enable" for index in range(4)),
        )
    },
}


@callback
def async_remove_setting_mirrors(
    hass: HomeAssistant, entry: ConfigEntry, *, remove_bitrate: bool = False
) -> None:
    """Retire only this entry's known configuration mirrors from the registry.

    Control, measurement and detection identities are preserved. Recorder data
    is not deleted; HA retains its normal deleted-entity metadata.
    """
    registry = er.async_get(hass)
    identifier = entry.unique_id or entry.entry_id
    # Preserve the legacy bitrate identity until telemetry confirms a replacement.
    retired = {
        (domain, f"{identifier}:{key}")
        for domain, key in SETTING_MIRRORS
        if key != "videoKbps" or remove_bitrate
    }
    for registered in er.async_entries_for_config_entry(registry, entry.entry_id):
        if (
            registered.platform == DOMAIN
            and (registered.domain, registered.unique_id) in retired
        ):
            registry.async_remove(registered.entity_id)


@callback
def async_remove_unsupported_controls(hass, entry, domain, known_keys, supported_keys):
    """Retire this entry's unsupported legacy controls after successful discovery."""
    registry = er.async_get(hass)
    identifier = entry.unique_id or entry.entry_id
    unsupported = {
        f"{identifier}:{key}" for key in set(known_keys) - set(supported_keys)
    }
    for registered in er.async_entries_for_config_entry(registry, entry.entry_id):
        if (
            registered.platform == DOMAIN
            and registered.domain == domain
            and registered.unique_id in unsupported
        ):
            registry.async_remove(registered.entity_id)
