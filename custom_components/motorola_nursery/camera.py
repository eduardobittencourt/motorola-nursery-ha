"""Camera entity for Motorola Nursery Local."""

from __future__ import annotations

from typing import override
from urllib.parse import quote

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.components.stream import CONF_RTSP_TRANSPORT
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import RuntimeData
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the camera entity."""
    async_add_entities([MotorolaNurseryCamera(entry)])


class MotorolaNurseryCamera(Camera):
    """Representation of a locally tunneled Motorola Nursery camera."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = CameraEntityFeature.STREAM
    _attr_is_streaming = True

    def __init__(self, entry: ConfigEntry) -> None:
        super().__init__()
        runtime: RuntimeData = entry.runtime_data
        self._runtime = runtime
        self._attr_unique_id = entry.unique_id or entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            manufacturer="Motorola Nursery",
            model="VM65",
            name=entry.title,
        )
        self.stream_options[CONF_RTSP_TRANSPORT] = "tcp"

    @property
    @override
    def use_stream_for_stills(self) -> bool:
        """Generate still images from the video stream."""
        return True

    @override
    async def stream_source(self) -> str:
        """Return the private loopback RTSP source."""
        credentials = self._runtime.credentials
        user = quote(credentials.rtsp_username, safe="")
        password = quote(credentials.rtsp_password, safe="")
        token = quote(credentials.access_token, safe="")
        return (
            f"rtsp://{user}:{password}@127.0.0.1:{self._runtime.bridge.port}"
            f"/owner/streaming?accessToken={token}"
        )

