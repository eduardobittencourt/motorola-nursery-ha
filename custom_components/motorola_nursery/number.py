"""Writable numeric settings validated against camera-advertised bounds."""

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import callback

from .entity import MotorolaTelemetryEntity

NUMBERS = (
    NumberEntityDescription(
        key="video_brightness",
        translation_key="video_brightness",
        icon="mdi:brightness-6",
        native_min_value=0,
        native_max_value=4,
        native_step=1,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
    ),
    NumberEntityDescription(
        key="speaker_volume",
        translation_key="speaker_volume",
        icon="mdi:volume-high",
        native_min_value=1,
        native_max_value=6,
        native_step=1,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
    ),
    NumberEntityDescription(
        key="motion",
        translation_key="motion",
        icon="mdi:motion-sensor",
        native_min_value=0,
        native_max_value=4,
        native_step=1,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
    ),
    NumberEntityDescription(
        key="sound",
        translation_key="sound",
        icon="mdi:microphone",
        native_min_value=0,
        native_max_value=5,
        native_step=1,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
    ),
    *(
        NumberEntityDescription(
            key=key,
            translation_key=key,
            device_class=NumberDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            native_min_value=minimum,
            native_max_value=maximum,
            native_step=1,
            mode=NumberMode.BOX,
            entity_category=EntityCategory.CONFIG,
        )
        for key, minimum, maximum in (
            ("temperature_low", 8, 24),
            ("temperature_high", 22, 36),
        )
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
            for item in NUMBERS
            if item.key in coordinator.data.capabilities and item.key not in added
        ]
        added.update(item.key for item in descriptions)
        async_add_entities(
            MotorolaNumber(coordinator, entry, item) for item in descriptions
        )

    entry.async_on_unload(coordinator.async_add_listener(discover))
    discover()


class MotorolaNumber(MotorolaTelemetryEntity, NumberEntity):
    def __init__(self, coordinator, entry, description):
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def native_value(self):
        return self.value

    async def async_set_native_value(self, value: float) -> None:
        if not value.is_integer():
            raise ValueError("Camera settings require whole numbers")
        await self.coordinator.async_set_value(self._key, int(value))
