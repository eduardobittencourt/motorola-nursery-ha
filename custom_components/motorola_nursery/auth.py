"""Home Assistant account storage and camera credential conversion."""

from __future__ import annotations

import asyncio
import hashlib
import ssl
from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .cloud import AuthenticationError, CloudClient, Device, Session
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_MAGIC_TOKEN,
    CONF_RTSP_PASSWORD,
    CONF_RTSP_USERNAME,
    CONF_SESSION,
    CONF_SID_DEVICE,
    CONF_SID_USER_ID,
    DOMAIN,
)
from .protocol import Credentials
from .vendor import RTSP_PASSWORD, RTSP_USERNAME


def credentials_from_data(data: Mapping[str, Any]) -> Credentials:
    return Credentials(
        int(data[CONF_SID_USER_ID]),
        data[CONF_SID_DEVICE].encode(),
        data[CONF_MAGIC_TOKEN].encode(),
        data[CONF_RTSP_USERNAME],
        data[CONF_RTSP_PASSWORD],
        data[CONF_ACCESS_TOKEN],
    )


def device_data(device: Device, previous: Mapping[str, Any] | None = None) -> dict:
    """Use app defaults for new cameras; preserve imported RTSP overrides."""
    previous = previous or {}
    password = previous.get(CONF_RTSP_PASSWORD, RTSP_PASSWORD)
    return {
        CONF_SID_USER_ID: device.owner_id,
        CONF_SID_DEVICE: device.sid_device,
        CONF_MAGIC_TOKEN: device.magic_token,
        CONF_RTSP_USERNAME: previous.get(CONF_RTSP_USERNAME, RTSP_USERNAME),
        CONF_RTSP_PASSWORD: password,
        # The camera protocol requires this legacy digest as an identifier. It is
        # not used as a password hash, signature, or other security primitive.
        CONF_ACCESS_TOKEN: hashlib.sha1(
            (device.magic_token + password).encode(), usedforsecurity=False
        ).hexdigest(),
        "model": device.model,
    }


def account_lock(hass: HomeAssistant, entry: ConfigEntry) -> asyncio.Lock:
    """Serialize renewals and reauthentication for the same entry."""
    locks = hass.data.setdefault(DOMAIN, {}).setdefault("account_locks", {})
    return locks.setdefault(entry.entry_id, asyncio.Lock())


async def async_client(hass: HomeAssistant, host: str | None = None) -> CloudClient:
    # Loading CA files must not block Home Assistant's event loop.
    context = await hass.async_add_executor_job(ssl.create_default_context)
    return CloudClient(context, host) if host else CloudClient(context)


async def async_refresh_credentials(
    hass: HomeAssistant, entry: ConfigEntry
) -> Credentials:
    """Persist rotated session BEFORE any subsequent fallible device operation."""
    async with account_lock(hass, entry):
        if CONF_SESSION not in entry.data:
            raise AuthenticationError("Account login required")
        try:
            session = Session.from_dict(entry.data[CONF_SESSION])
        except (ValueError, KeyError, TypeError):
            raise AuthenticationError("Account login required") from None
        client = await async_client(hass, session.host)
        try:
            await client.connect()
            renewed = await client.resume(session)
            hass.config_entries.async_update_entry(
                entry,
                data={**entry.data, CONF_SESSION: renewed.as_dict()},
            )
            devices = await client.devices()
            device = next((d for d in devices if d.sid_device == entry.unique_id), None)
            if device is None:
                raise AuthenticationError("Camera is no longer in this account")
            data = {**entry.data, **device_data(device, entry.data)}
            hass.config_entries.async_update_entry(entry, data=data)
            return credentials_from_data(data)
        finally:
            await client.close()
