"""Momentary PTZ controls for the verified VM65 command set."""

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory

from .entity import MotorolaCoordinatorEntity

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
    if coordinator is None or not entry.data.get("model", "VM65").upper().startswith(
        "VM65"
    ):
        return
    async_add_entities(MotorolaPtzButton(coordinator, entry, item) for item in BUTTONS)


class MotorolaPtzButton(MotorolaCoordinatorEntity, ButtonEntity):
    def __init__(self, coordinator, entry, description):
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        axis, direction = PTZ_COMMANDS[self._key]
        await self.coordinator.async_ptz(axis, direction)
