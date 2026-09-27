"""Shared identity and availability for read-only telemetry entities."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MotorolaTelemetryCoordinator


class MotorolaTelemetryEntity(CoordinatorEntity[MotorolaTelemetryCoordinator]):
    """Attach sensors to the existing camera, including imported entries."""

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

    @property
    def available(self) -> bool:
        return super().available and self.value is not None

    @property
    def value(self) -> int | str | None:
        data = self.coordinator.data
        return data.values.get(self._key) if data else None
