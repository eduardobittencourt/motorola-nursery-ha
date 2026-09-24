"""Motorola Nursery Local integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import quote

from homeassistant.components.ffmpeg import get_ffmpeg_manager
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .bridge import RtspBridge
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_MAGIC_TOKEN,
    CONF_RTSP_PASSWORD,
    CONF_RTSP_USERNAME,
    CONF_SID_DEVICE,
    CONF_SID_USER_ID,
    PLATFORMS,
)
from .protocol import Credentials
from .transcoder import FfmpegRelay

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class RuntimeData:
    """Runtime objects owned by a config entry."""

    bridge: RtspBridge
    relay: FfmpegRelay


def credentials_from_entry(entry: ConfigEntry) -> Credentials:
    """Convert a config entry to validated protocol credentials."""
    credentials = Credentials(
        sid_user_id=int(entry.data[CONF_SID_USER_ID]),
        sid_device=entry.data[CONF_SID_DEVICE].encode(),
        magic_token=entry.data[CONF_MAGIC_TOKEN].encode(),
        rtsp_username=entry.data[CONF_RTSP_USERNAME],
        rtsp_password=entry.data[CONF_RTSP_PASSWORD],
        access_token=entry.data[CONF_ACCESS_TOKEN],
    )
    credentials.validate()
    return credentials


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Motorola Nursery Local from a config entry."""
    credentials = credentials_from_entry(entry)

    def log_connection_error(err: Exception) -> None:
        _LOGGER.debug("Local camera tunnel closed: %s", type(err).__name__)

    bridge = RtspBridge(entry.data["host"], credentials, log_connection_error)
    await bridge.start()
    user = quote(credentials.rtsp_username, safe="")
    password = quote(credentials.rtsp_password, safe="")
    token = quote(credentials.access_token, safe="")
    input_url = (
        f"rtsp://{user}:{password}@127.0.0.1:{bridge.port}"
        f"/owner/streaming?accessToken={token}"
    )

    def log_process_error(return_code: int) -> None:
        _LOGGER.debug("Local audio transcoder exited with code %d", return_code)

    relay = FfmpegRelay(get_ffmpeg_manager(hass).binary, input_url, log_process_error)
    await relay.start()
    entry.runtime_data = RuntimeData(bridge, relay)
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        await relay.stop()
        await bridge.stop()
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an entry and its loopback bridge."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    await entry.runtime_data.relay.stop()
    await entry.runtime_data.bridge.stop()
    return True
