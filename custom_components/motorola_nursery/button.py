"""Momentary PTZ controls discovered from individual camera capabilities."""

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import callback

from .capabilities import ptz_supported
from .entity import MotorolaCoordinatorEntity, async_remove_unsupported_controls

PTZ_COMMANDS = {
    "ptz_pan_left": ("pan", "left"),
    "ptz_pan_right": ("pan", "right"),
    "ptz_tilt_up": ("tilt", "up"),
    "ptz_tilt_down": ("tilt", "down"),
    "ptz_origin": ("ptz", "origin"),
}

BUTTONS = tuple(
    ButtonEntityDescription(
        key=key,
        translation_key=key,
        icon=icon,
        entity_category=EntityCategory.CONFIG,
    )
    for key, icon in (
        ("ptz_pan_left", "mdi:arrow-left-bold"),
        ("ptz_pan_right", "mdi:arrow-right-bold"),
        ("ptz_tilt_up", "mdi:arrow-up-bold"),
        ("ptz_tilt_down", "mdi:arrow-down-bold"),
        ("ptz_origin", "mdi:camera-control"),
    )
)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data.telemetry
    if coordinator is None:
        return
    added = set()
    discovered = False

    @callback
    def discover():
        nonlocal discovered
        if not coordinator.last_update_success or coordinator.data is None:
            return
        supported = [
            item
            for item in BUTTONS
            if ptz_supported(coordinator.data, PTZ_COMMANDS[item.key][0])
        ]
        if not discovered:
            async_remove_unsupported_controls(
                hass, entry, "button", PTZ_COMMANDS, (item.key for item in supported)
            )
            discovered = True
        descriptions = [item for item in supported if item.key not in added]
        added.update(item.key for item in descriptions)
        async_add_entities(
            MotorolaPtzButton(coordinator, entry, item) for item in descriptions
        )

    entry.async_on_unload(coordinator.async_add_listener(discover))
    discover()


class MotorolaPtzButton(MotorolaCoordinatorEntity, ButtonEntity):
    def __init__(self, coordinator, entry, description):
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def available(self):
        return super().available and ptz_supported(
            self.coordinator.data, PTZ_COMMANDS[self._key][0]
        )

    async def async_press(self) -> None:
        axis, direction = PTZ_COMMANDS[self._key]
        await self.coordinator.async_ptz(axis, direction)
