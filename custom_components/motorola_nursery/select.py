"""Writable enumerated camera settings."""

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import callback

from .entity import MotorolaTelemetryEntity

OPTION_VALUES = {
    "night_vision": {"off": 0, "on": 1, "auto": 2},
    "video_bitrate": {
        "160_kbit_s": 0,
        "480_kbit_s": 1,
        "640_kbit_s": 2,
        "1000_kbit_s": 3,
    },
    "video_light_frequency": {"50_hz": 0, "60_hz": 1},
}

SELECTS = (
    SelectEntityDescription(
        key="night_vision",
        translation_key="night_vision",
        icon="mdi:weather-night",
        options=tuple(OPTION_VALUES["night_vision"]),
        entity_category=EntityCategory.CONFIG,
    ),
    SelectEntityDescription(
        key="video_bitrate",
        translation_key="video_bitrate",
        icon="mdi:video-high-definition",
        options=tuple(OPTION_VALUES["video_bitrate"]),
        entity_category=EntityCategory.CONFIG,
    ),
    SelectEntityDescription(
        key="video_light_frequency",
        translation_key="video_light_frequency",
        icon="mdi:sine-wave",
        options=tuple(OPTION_VALUES["video_light_frequency"]),
        entity_category=EntityCategory.CONFIG,
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
            for item in SELECTS
            if item.key in coordinator.data.capabilities and item.key not in added
        ]
        added.update(item.key for item in descriptions)
        async_add_entities(
            MotorolaSelect(coordinator, entry, item) for item in descriptions
        )

    entry.async_on_unload(coordinator.async_add_listener(discover))
    discover()


class MotorolaSelect(MotorolaTelemetryEntity, SelectEntity):
    def __init__(self, coordinator, entry, description):
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def current_option(self):
        value = self.value
        return next(
            (
                option
                for option, raw in OPTION_VALUES[self._key].items()
                if raw == value
            ),
            None,
        )

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_value(
            self._key, OPTION_VALUES[self._key][option]
        )
