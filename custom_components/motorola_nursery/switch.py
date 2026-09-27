"""Writable boolean camera settings."""

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import callback

from .entity import MotorolaTelemetryEntity

SWITCHES = (
    *(
        SwitchEntityDescription(
            key=key,
            translation_key=translation,
            icon=icon,
            entity_category=EntityCategory.CONFIG,
        )
        for key, translation, icon in (
            ("ceiling_mount", "ceiling_mount", "mdi:image-flip-vertical"),
            ("lowtemp_switch", "low_temperature_alert", "mdi:thermometer-low"),
            ("hightemp_switch", "high_temperature_alert", "mdi:thermometer-high"),
            ("video[0].motion_zone", "motion_zones", "mdi:motion-sensor"),
        )
    ),
    *(
        SwitchEntityDescription(
            key=f"video[0].motion.zone[{index}].enable",
            translation_key=f"motion_zone_{index + 1}",
            icon="mdi:motion-sensor",
            entity_category=EntityCategory.CONFIG,
        )
        for index in range(4)
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data.telemetry
    if coordinator is None:
        return
    added: set[str] = set()

    @callback
    def discover():
        if not coordinator.last_update_success or coordinator.data is None:
            return
        descriptions = [
            item
            for item in SWITCHES
            if item.key in coordinator.data.capabilities and item.key not in added
        ]
        added.update(item.key for item in descriptions)
        async_add_entities(
            MotorolaSwitch(coordinator, entry, item) for item in descriptions
        )

    entry.async_on_unload(coordinator.async_add_listener(discover))
    discover()


class MotorolaSwitch(MotorolaTelemetryEntity, SwitchEntity):
    def __init__(self, coordinator, entry, description):
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def is_on(self):
        return bool(self.value) if self.value in (0, 1) else None

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_set_value(self._key, 1)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_set_value(self._key, 0)
