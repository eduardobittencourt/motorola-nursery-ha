"""Writable enumerated camera settings."""

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import callback

from .capabilities import OPTION_VALUES, options, setting_supported
from .entity import MotorolaSettingEntity, async_remove_unsupported_controls

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
    discovered = False

    @callback
    def discover():
        nonlocal discovered
        if not coordinator.last_update_success or coordinator.data is None:
            return
        descriptions = [
            item
            for item in SELECTS
            if setting_supported(coordinator.data, item.key) and item.key not in added
        ]
        if not discovered:
            async_remove_unsupported_controls(
                hass,
                entry,
                "select",
                (item.key for item in SELECTS),
                (item.key for item in descriptions),
            )
            discovered = True
        added.update(item.key for item in descriptions)
        async_add_entities(
            MotorolaSelect(coordinator, entry, item) for item in descriptions
        )

    entry.async_on_unload(coordinator.async_add_listener(discover))
    discover()


class MotorolaSelect(MotorolaSettingEntity, SelectEntity):
    def __init__(self, coordinator, entry, description):
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def options(self):
        return options(self.coordinator.data, self._key)

    @property
    def available(self):
        return super().available and self.current_option in self.options

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
