"""Shared sensor polling, independent of local video and account renewal."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .auth import credentials_from_data
from .cloud import vendor_host
from .const import CONF_SESSION, DOMAIN
from .telemetry import TelemetryClient, TelemetryData, TelemetryError

_LOGGER = logging.getLogger(__name__)


class MotorolaTelemetryCoordinator(DataUpdateCoordinator[TelemetryData]):
    """A telemetry failure never reloads the entry or interrupts the video."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: TelemetryClient
    ):
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=60),
            always_update=False,
        )
        self.client = client
        self.entry = entry

    def _credentials(self):
        self.client.host = vendor_host(self.entry.data[CONF_SESSION]["host"])
        return credentials_from_data(self.entry.data)

    def _set_values(self, **updates: int | str) -> None:
        if self.data is None:
            return
        values = dict(self.data.values)
        values.update(updates)
        self.async_set_updated_data(TelemetryData(dict(self.data.capabilities), values))

    async def _async_update_data(self) -> TelemetryData:
        try:
            # Read current credentials after any video-driven credential renewal.
            data = await self.client.async_read(self._credentials())
        except (TelemetryError, ValueError, KeyError):
            raise UpdateFailed("Camera telemetry unavailable") from None
        registry = dr.async_get(self.hass)
        device = registry.async_get_device_by_identifier(
            (DOMAIN, self.entry.unique_id or self.entry.entry_id), self.entry.entry_id
        )
        if device is not None:
            versions = {
                field: data.values[key]
                for field, key in (
                    ("sw_version", "firmware_version"),
                    ("hw_version", "hardware_version"),
                )
                if isinstance(data.values.get(key), str)
            }
            if versions:
                registry.async_update_device(device.id, **versions)
        return data

    async def async_set_value(self, key: str, value: int) -> None:
        """Write and immediately publish one confirmed setting."""
        try:
            confirmed = await self.client.async_set(self._credentials(), key, value)
        except (TelemetryError, ValueError, KeyError):
            raise HomeAssistantError("Camera setting unavailable") from None
        updates = {key: confirmed}
        if key == "video_bitrate":
            updates["videoKbps"] = (160, 480, 640, 1000)[confirmed]
        self._set_values(**updates)

    async def async_list_songs(self) -> tuple[str, ...]:
        try:
            return await self.client.async_list_songs(self._credentials())
        except (TelemetryError, ValueError, KeyError):
            raise HomeAssistantError("Camera playlist unavailable") from None

    async def async_play(self, song: str) -> None:
        try:
            await self.client.async_play(self._credentials(), song)
        except (TelemetryError, ValueError, KeyError):
            raise HomeAssistantError("Lullaby playback unavailable") from None
        self._set_values(playing=song, audio_control=1)

    async def async_stop_playback(self) -> None:
        try:
            await self.client.async_stop(self._credentials())
        except (TelemetryError, ValueError, KeyError):
            raise HomeAssistantError("Lullaby stop unavailable") from None
        self._set_values(playing="(none)", audio_control=0)

    async def async_ptz(self, axis: str, direction: str) -> None:
        try:
            await self.client.async_ptz(self._credentials(), axis, direction)
        except (TelemetryError, ValueError, KeyError):
            raise HomeAssistantError("Camera movement unavailable") from None
