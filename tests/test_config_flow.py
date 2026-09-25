"""Native HA onboarding, reconfiguration and safe failure behavior."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.motorola_nursery.auth import device_data
from custom_components.motorola_nursery.cloud import (
    AuthenticationError,
    Challenge,
    Device,
    Session,
)
from custom_components.motorola_nursery.config_flow import ConfigFlow
from custom_components.motorola_nursery.const import DOMAIN

DEVICE = Device(
    "123456",
    "device-identifier",
    "VM65",
    "Nursery%20Test",
    "test-magic-token",
    "abcdefghijklmnopqrst",
    "-1",
)
SESSION = Session("123456", "synthetic-token", "1234567", "9.moto.5gencare.com")


def make_client():
    client = AsyncMock()
    client.host = SESSION.host
    client.request_code.return_value = Challenge("123456", SESSION.host)
    client.submit_code.return_value = SESSION
    client.devices.return_value = [DEVICE]
    return client


def make_flow(hass, source="user", entry=None):
    flow = ConfigFlow()
    flow.hass = hass
    flow.context = {"source": source}
    if entry:
        flow.context["entry_id"] = entry.entry_id
    return flow


@pytest.mark.asyncio
async def test_full_ui_flow(hass):
    flow = make_flow(hass)
    client = make_client()
    with (
        patch(
            "custom_components.motorola_nursery.config_flow.async_client",
            AsyncMock(return_value=client),
        ),
        patch(
            "custom_components.motorola_nursery.config_flow.MagicP2PTunnel.connect",
            AsyncMock(return_value=AsyncMock()),
        ),
    ):
        result = await flow.async_step_user()
        assert result["step_id"] == "user"
        client.request_code.assert_not_called()
        result = await flow.async_step_user({"email": "owner@example.test"})
        assert result["step_id"] == "code"
        result = await flow.async_step_code({"code": "123456"})
        assert result["step_id"] == "device"
        result = await flow.async_step_device({"device": DEVICE.sid_device})
        assert result["step_id"] == "host"
        result = await flow.async_step_host({"host": "192.0.2.10"})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["cloud_session"]["token"] == SESSION.token
    assert result["data"]["sid_device"] == DEVICE.sid_device
    assert "code" not in result["data"]
    client.request_code.assert_awaited_once()
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_invalid_code_retry_does_not_send_new_email(hass):
    flow = make_flow(hass)
    client = make_client()
    client.submit_code.side_effect = [AuthenticationError(), SESSION]
    with patch(
        "custom_components.motorola_nursery.config_flow.async_client",
        AsyncMock(return_value=client),
    ):
        await flow.async_step_user({"email": "owner@example.test"})
        result = await flow.async_step_code({"code": "000000"})
        assert result["errors"] == {"code": "invalid_code"}
        assert "default" not in str(result["data_schema"])
        result = await flow.async_step_code({"code": "123456"})
    assert result["step_id"] == "device"
    client.request_code.assert_awaited_once()


@pytest.mark.asyncio
async def test_reconfigure_preserves_entry_and_id(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DEVICE.sid_device,
        data={**device_data(DEVICE), "host": "192.0.2.10"},
        title="Existing camera",
    )
    entry.add_to_hass(hass)
    flow = make_flow(hass, config_entries.SOURCE_RECONFIGURE, entry)
    client = make_client()
    with (
        patch(
            "custom_components.motorola_nursery.config_flow.async_client",
            AsyncMock(return_value=client),
        ),
        patch(
            "custom_components.motorola_nursery.config_flow.MagicP2PTunnel.connect",
            AsyncMock(return_value=AsyncMock()),
        ),
        patch.object(hass.config_entries, "async_schedule_reload"),
    ):
        assert (await flow.async_step_reconfigure())["type"] == FlowResultType.MENU
        await flow.async_step_user({"email": "owner@example.test"})
        assert (await flow.async_step_code({"code": "123456"}))["step_id"] == "host"
        result = await flow.async_step_host({"host": "192.0.2.11"})
    assert result["reason"] == "reconfigure_successful"
    assert entry.unique_id == DEVICE.sid_device
    assert entry.title == "Existing camera"
    assert entry.data["host"] == "192.0.2.11"
    assert entry.data["cloud_session"]["token"] == SESSION.token


@pytest.mark.asyncio
async def test_wrong_account_does_not_modify_entry(hass):
    original = {**device_data(DEVICE), "host": "192.0.2.10"}
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DEVICE.sid_device, data=original)
    entry.add_to_hass(hass)
    flow = make_flow(hass, config_entries.SOURCE_REAUTH, entry)
    client = make_client()
    client.devices.return_value = []
    with patch(
        "custom_components.motorola_nursery.config_flow.async_client",
        AsyncMock(return_value=client),
    ):
        assert (await flow.async_step_reauth(entry.data))["step_id"] == "user"
        await flow.async_step_user({"email": "other@example.test"})
        result = await flow.async_step_code({"code": "123456"})
    assert result["reason"] == "wrong_account"
    assert entry.data == original


@pytest.mark.asyncio
async def test_device_list_retry_does_not_replay_code(hass):
    flow = make_flow(hass)
    first, second = make_client(), make_client()
    first.devices.side_effect = TimeoutError()
    second.resume.return_value = Session(
        "123456", "rotated-token", "1234567", SESSION.host
    )
    with patch(
        "custom_components.motorola_nursery.config_flow.async_client",
        AsyncMock(side_effect=[first, second]),
    ):
        await flow.async_step_user({"email": "owner@example.test"})
        result = await flow.async_step_code({"code": "123456"})
        assert result["step_id"] == "devices"
        result = await flow.async_step_devices({})
    assert result["step_id"] == "device"
    assert flow._session.token == "rotated-token"
    first.submit_code.assert_awaited_once()
    second.submit_code.assert_not_called()
    second.request_code.assert_not_called()


@pytest.mark.asyncio
async def test_real_ha_flow_manager_and_abort_cleanup(hass):
    client = make_client()
    with (
        patch(
            "custom_components.motorola_nursery.config_flow.async_client",
            AsyncMock(return_value=client),
        ),
        patch("homeassistant.config_entries.async_process_deps_reqs", AsyncMock()),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        assert result["step_id"] == "user"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"email": "owner@example.test"}
        )
        assert result["step_id"] == "code"
        hass.config_entries.flow.async_abort(result["flow_id"])
        await hass.async_block_till_done()
    client.close.assert_awaited_once()
