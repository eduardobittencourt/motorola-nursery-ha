"""Native Home Assistant event entities for camera detections."""

from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN

EVENTS = (
    ("motion", "motion_detected", EventDeviceClass.MOTION, "mdi:motion-sensor"),
    ("sound", "sound_detected", None, "mdi:microphone"),
)


async def async_setup_entry(hass, entry, async_add_entities):
    manager = entry.runtime_data.events
    if manager is None:
        return
    async_add_entities(
        MotorolaDetectionEvent(manager, entry, *description) for description in EVENTS
    )


class MotorolaDetectionEvent(EventEntity):
    """Represent every detection, including repeated detections close together."""

    _attr_has_entity_name = True
    _attr_event_types = ["detected"]

    def __init__(
        self, manager, entry: ConfigEntry, key, translation_key, device_class, icon
    ):
        self.manager = manager
        self._key = key
        self._attr_translation_key = translation_key
        self._attr_device_class = device_class
        self._attr_icon = icon
        identifier = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{identifier}:{key}_event"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, identifier)},
            manufacturer="Motorola Nursery",
            model=entry.data.get("model", "VM65"),
            name=entry.title,
        )

    @property
    def available(self):
        return self.manager.connected

    async def async_added_to_hass(self):
        self.async_on_remove(self.manager.async_add_listener(self._handle_event))

    def _handle_event(self, event):
        if event is not None and event.event_type == self._key:
            self._trigger_event(
                "detected", {"detected_at": event.detected_at.isoformat()}
            )
        self.async_write_ha_state()
