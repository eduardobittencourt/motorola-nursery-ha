"""Camera measurements, separate from configuration controls."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.core import callback

from .capabilities import options, setting_supported
from .entity import MotorolaTelemetryEntity, async_remove_setting_mirrors
from .select import OPTION_VALUES

SENSORS = (
    SensorEntityDescription(
        key="temperature_reading",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="wifi_signal",
        translation_key="wifi_signal",
        icon="mdi:wifi",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="videoKbps",
        translation_key="video_bitrate",
        icon="mdi:speedometer",
        native_unit_of_measurement="kbit/s",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Discover entities on first success, even after a cloud outage at startup."""
    coordinator = entry.runtime_data.telemetry
    if coordinator is None:
        return
    added: set[str] = set()

    @callback
    def discover():
        if not coordinator.last_update_success or coordinator.data is None:
            return
        capabilities = coordinator.data.capabilities
        bitrate_control_ready = setting_supported(
            coordinator.data, "video_bitrate"
        ) and any(
            coordinator.data.values.get("video_bitrate")
            == OPTION_VALUES["video_bitrate"][name]
            for name in options(coordinator.data, "video_bitrate")
        )
        if bitrate_control_ready:
            async_remove_setting_mirrors(hass, entry, remove_bitrate=True)
            added.discard("videoKbps")
        descriptions = [
            item
            for item in SENSORS
            if item.key in capabilities
            and item.key not in added
            and (item.key != "videoKbps" or not bitrate_control_ready)
        ]
        added.update(item.key for item in descriptions)
        async_add_entities(
            MotorolaSensor(coordinator, entry, item) for item in descriptions
        )

    entry.async_on_unload(coordinator.async_add_listener(discover))
    discover()


class MotorolaSensor(MotorolaTelemetryEntity, SensorEntity):
    """A sensor cannot write settings or activate camera hardware."""

    def __init__(self, coordinator, entry, description):
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def native_value(self):
        value = self.value
        if self._key == "temperature_reading":
            return value / 10 if isinstance(value, int) else None
        return value

    @property
    def available(self):
        return super().available and self.native_value is not None
