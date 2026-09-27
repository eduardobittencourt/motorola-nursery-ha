"""Shared sensor polling, independent of local video and account renewal."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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

    async def _async_update_data(self) -> TelemetryData:
        try:
            self.client.host = vendor_host(self.entry.data[CONF_SESSION]["host"])
            # Read current credentials after any video-driven credential renewal.
            data = await self.client.async_read(credentials_from_data(self.entry.data))
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
