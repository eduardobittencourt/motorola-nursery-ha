"""Real-time motion and sound detections."""

import asyncio

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    manager = entry.runtime_data.events
    if manager is not None:
        async_add_entities(
            MotorolaDetectionBinarySensor(
                manager, entry, key, translation, device_class
            )
            for key, translation, device_class in (
                ("motion", "motion_detected", "motion"),
                ("sound", "sound_detected", "sound"),
            )
        )


class MotorolaDetectionBinarySensor(BinarySensorEntity):
    """Pulse for ten seconds after each real camera detection."""

    _attr_has_entity_name = True

    def __init__(self, manager, entry, key, translation_key, device_class):
        self.manager = manager
        self._key = key
        self._attr_translation_key = translation_key
        self._attr_device_class = device_class
        self._attr_is_on = False
        self._clear_handle: asyncio.TimerHandle | None = None
        identifier = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{identifier}:{key}_detected"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, identifier)},
            manufacturer="Motorola Nursery",
            model=entry.data.get("model", "VM65"),
            name=entry.title,
        )

    @property
    def available(self):
        return self.manager.connected

    @property
    def extra_state_attributes(self):
        detected_at = self.manager.latest.get(self._key)
        return {"last_detected": detected_at.isoformat() if detected_at else None}

    async def async_added_to_hass(self):
        self.async_on_remove(self.manager.async_add_listener(self._handle_event))

    async def async_will_remove_from_hass(self):
        if self._clear_handle is not None:
            self._clear_handle.cancel()

    @callback
    def _handle_event(self, event):
        if event is not None and event.event_type == self._key:
            self._attr_is_on = True
            if self._clear_handle is not None:
                self._clear_handle.cancel()
            self._clear_handle = self.hass.loop.call_later(10, self._clear)
        self.async_write_ha_state()

    @callback
    def _clear(self):
        self._clear_handle = None
        self._attr_is_on = False
        self.async_write_ha_state()
