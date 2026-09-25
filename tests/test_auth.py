"""Rotating-token persistence and playback recovery against real HA entries."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.motorola_nursery import RuntimeData
from custom_components.motorola_nursery.auth import (
    async_refresh_credentials,
    credentials_from_data,
    device_data,
)
from custom_components.motorola_nursery.cloud import (
    AuthenticationError,
    Device,
    Session,
)
from custom_components.motorola_nursery.const import DOMAIN
from custom_components.motorola_nursery.diagnostics import (
    async_get_config_entry_diagnostics,
)

DEVICE = Device(
    "123456", "opaque", "VM65", "Nursery", "test-token", "abcdefghijklmnopqrst", "-1"
)
OLD = Session("123456", "old-test-token", "1234567", "9.moto.5gencare.com")
NEW = Session("123456", "new-test-token", "1234567", "9.moto.5gencare.com")


def entry_for(hass, account=True):
    data = {**device_data(DEVICE), "host": "192.0.2.10"}
    if account:
        data.update(cloud_session=OLD.as_dict(), email="owner@example.test")
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DEVICE.sid_device, data=data)
    entry.add_to_hass(hass)
    return entry


@pytest.mark.asyncio
async def test_rotated_token_survives_list_failure(hass):
    entry = entry_for(hass)
    client = AsyncMock()
    client.resume.return_value = NEW

    async def fail_devices():
        assert entry.data["cloud_session"]["token"] == NEW.token
        raise TimeoutError()

    client.devices.side_effect = fail_devices
    with (
        patch(
            "custom_components.motorola_nursery.auth.async_client",
            AsyncMock(return_value=client),
        ),
        pytest.raises(TimeoutError),
    ):
        await async_refresh_credentials(hass, entry)
    assert entry.data["cloud_session"]["token"] == NEW.token
    assert entry.data["magic_token"] == DEVICE.magic_token
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_concurrent_refresh_uses_latest_token(hass):
    entry = entry_for(hass)
    first, second = AsyncMock(), AsyncMock()
    first.resume.return_value = NEW
    final = Session("123456", "final-test-token", "1234567", OLD.host)
    second.resume.return_value = final
    first.devices.return_value = second.devices.return_value = [DEVICE]
    with patch(
        "custom_components.motorola_nursery.auth.async_client",
        AsyncMock(side_effect=[first, second]),
    ):
        await asyncio.gather(
            async_refresh_credentials(hass, entry),
            async_refresh_credentials(hass, entry),
        )
    first.resume.assert_awaited_once_with(OLD)
    second.resume.assert_awaited_once_with(NEW)
    assert entry.data["cloud_session"]["token"] == final.token


@pytest.mark.asyncio
async def test_runtime_recovery_is_serialized_and_updates_sources(hass):
    entry = entry_for(hass)
    bridge, relay = Mock(), Mock()
    bridge.port = 12345
    runtime = RuntimeData(hass, entry, bridge, relay, credentials_from_data(entry.data))
    new_device = Device(
        "123456",
        "opaque",
        "VM65",
        "Nursery",
        "new-magic-token",
        DEVICE.sid_device,
        "-1",
    )
    new_credentials = credentials_from_data(device_data(new_device))
    refresh = AsyncMock(return_value=new_credentials)
    local = AsyncMock(side_effect=[ConnectionError(), AsyncMock()])
    with (
        patch("custom_components.motorola_nursery.async_refresh_credentials", refresh),
        patch("custom_components.motorola_nursery.MagicP2PTunnel.connect", local),
    ):
        await asyncio.gather(
            runtime.async_prepare_stream(), runtime.async_prepare_stream()
        )
    refresh.assert_awaited_once()
    bridge.update_credentials.assert_called_once_with(new_credentials)
    relay.update_input_url.assert_called_once()
    assert runtime.credentials is new_credentials


@pytest.mark.asyncio
async def test_good_local_credentials_need_no_cloud_and_legacy_works(hass):
    for account in [False, True]:
        entry = entry_for(hass, account=account)
        runtime = RuntimeData(
            hass, entry, Mock(), Mock(), credentials_from_data(entry.data)
        )
        with (
            patch(
                "custom_components.motorola_nursery.async_refresh_credentials",
                AsyncMock(),
            ) as refresh,
            patch(
                "custom_components.motorola_nursery.MagicP2PTunnel.connect",
                AsyncMock(return_value=AsyncMock()),
            ),
        ):
            await runtime.async_prepare_stream()
        refresh.assert_not_called()


@pytest.mark.asyncio
async def test_rejected_cloud_session_starts_reauth_without_email(hass):
    entry = entry_for(hass)
    runtime = RuntimeData(
        hass, entry, Mock(), Mock(), credentials_from_data(entry.data)
    )
    with (
        patch(
            "custom_components.motorola_nursery.async_refresh_credentials",
            AsyncMock(side_effect=AuthenticationError()),
        ),
        patch(
            "custom_components.motorola_nursery.MagicP2PTunnel.connect",
            AsyncMock(side_effect=ConnectionError()),
        ),
        patch.object(entry, "async_start_reauth") as reauth,
    ):
        with pytest.raises(HomeAssistantError, match="needs authentication"):
            await runtime.async_prepare_stream()
        reauth.assert_called_once_with(hass)


@pytest.mark.asyncio
async def test_diagnostics_excludes_all_account_and_device_data(hass):
    entry = entry_for(hass)
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert set(result) == {"entry_version", "account_login_configured", "entry_state"}
    assert result["account_login_configured"] is True


@pytest.mark.asyncio
async def test_background_recovery_is_single_and_cancelled_on_unload(hass):
    entry = entry_for(hass)
    bridge, relay = Mock(), Mock()
    bridge.stop = AsyncMock()
    relay.stop = AsyncMock()
    runtime = RuntimeData(hass, entry, bridge, relay, credentials_from_data(entry.data))
    started = asyncio.Event()

    async def pending_prepare(self, *, force=False):
        assert force is True
        started.set()
        await asyncio.Future()

    with patch.object(RuntimeData, "async_prepare_stream", pending_prepare):
        runtime.recover_after_tunnel_error()
        first_task = runtime.recovery_task
        runtime.recover_after_tunnel_error()
        assert runtime.recovery_task is first_task
        await asyncio.wait_for(started.wait(), 1)
        await runtime.async_stop()
        assert first_task.cancelled()
        runtime.recover_after_tunnel_error()
        assert runtime.recovery_task is first_task
    relay.stop.assert_awaited_once()
    bridge.stop.assert_awaited_once()
