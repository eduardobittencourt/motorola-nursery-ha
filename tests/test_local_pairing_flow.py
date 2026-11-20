"""Native HA pairing flow: cancellation, expiry, failure and local-only storage."""

import asyncio
from contextlib import ExitStack
from dataclasses import replace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.data_entry_flow import FlowResultType

from custom_components.motorola_nursery.bootstrap import (
    LocalClockServer,
    LocalEnrollment,
    LocalHttpDnsServer,
)
from custom_components.motorola_nursery.const import DOMAIN
from custom_components.motorola_nursery.local import LocalControlServer

SETTINGS = {
    "ssid": "Synthetic nursery",
    "wifi_password": "synthetic wifi password",
    "host": "192.168.12.2",
    "local_server": "192.168.12.3",
}


@pytest.fixture
def pairing_resources(hass, socket_enabled):
    clock = LocalClockServer(0)
    control = LocalControlServer(0)
    enrollment = LocalEnrollment(SETTINGS["host"], 0)
    hass.data[DOMAIN] = {
        "local_clock_server": clock,
        "local_control_server": control,
        "local_httpdns_server": LocalHttpDnsServer(0),
    }
    with ExitStack() as stack:
        stack.enter_context(
            patch("homeassistant.config_entries.async_process_deps_reqs", AsyncMock())
        )
        stack.enter_context(
            patch(
                "custom_components.motorola_nursery.config_flow_local.LocalEnrollment",
                return_value=enrollment,
            )
        )
        stack.enter_context(
            patch(
                "custom_components.motorola_nursery.config_flow.async_client",
                side_effect=AssertionError("Cloud access forbidden"),
            )
        )
        yield clock, control, enrollment, stack


async def start(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == FlowResultType.MENU
    assert result["menu_options"] == ["local_pairing", "account"]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "local_pairing"}
    )
    assert result["step_id"] == "local_pairing"
    return await hass.config_entries.flow.async_configure(result["flow_id"], SETTINGS)


def assert_closed(clock, control, enrollment):
    assert clock.server is None and not clock.peers and not clock.tasks
    assert control._server is None and not control._entries and not control._tasks
    assert enrollment.server is None and not enrollment.tasks


async def test_native_qr_abort_removes_all_listeners_and_wifi(hass, pairing_resources):
    clock, control, enrollment, _ = pairing_resources
    result = await start(hass)
    assert result["step_id"] == "local_scan"
    schema = result["data_schema"].schema
    qr = next(iter(schema.values())).config["data"]
    assert "Synthetic%20nursery" in qr
    flow = hass.config_entries.flow._progress[result["flow_id"]]
    assert flow._pairing_qr == qr
    hass.config_entries.flow.async_abort(result["flow_id"])
    await hass.async_block_till_done()
    assert_closed(clock, control, enrollment)
    httpdns = hass.data[DOMAIN]["local_httpdns_server"]
    assert httpdns.server is None and not httpdns.peers and not httpdns.tasks
    assert not flow._pairing_qr
    assert next(iter(schema.values())).config["data"] == ""
    assert not hass.config_entries.async_entries(DOMAIN)


@pytest.mark.parametrize("listener", ["enrollment", "httpdns"])
async def test_port_conflict_rolls_back_every_partial_listener(
    hass, pairing_resources, listener
):
    clock, control, enrollment, stack = pairing_resources
    stack.enter_context(
        patch.object(
            enrollment
            if listener == "enrollment"
            else hass.data[DOMAIN]["local_httpdns_server"],
            "start",
            AsyncMock(side_effect=OSError),
        )
    )
    result = await start(hass)
    assert result["errors"] == {"base": "pairing_ports_unavailable"}
    httpdns = hass.data[DOMAIN]["local_httpdns_server"]
    assert httpdns.server is None and not httpdns.peers and not httpdns.tasks
    assert_closed(clock, control, enrollment)
    hass.config_entries.flow.async_abort(result["flow_id"])
    await hass.async_block_till_done()


async def test_expired_qr_closes_listeners_without_user_submission(
    hass, pairing_resources
):
    clock, control, enrollment, stack = pairing_resources
    stack.enter_context(
        patch(
            "custom_components.motorola_nursery.config_flow_local.PAIRING_SECONDS", 0.02
        )
    )
    closed = asyncio.Event()
    original_stop = clock.stop

    async def stop_and_signal():
        await original_stop()
        closed.set()

    stack.enter_context(patch.object(clock, "stop", side_effect=stop_and_signal))
    result = await start(hass)
    selector = next(iter(result["data_schema"].schema.values()))
    await asyncio.wait_for(closed.wait(), 1)
    assert selector.config["data"] == ""
    assert_closed(clock, control, enrollment)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["reason"] == "pairing_expired"


@pytest.mark.parametrize("probe_failure", [False, True])
async def test_local_pairing_verifies_control_and_video_before_storage(
    hass, pairing_resources, probe_failure
):
    clock, control, enrollment, stack = pairing_resources
    probe = stack.enter_context(
        patch(
            "custom_components.motorola_nursery.config_flow_local.MagicP2PTunnel.connect",
            AsyncMock(return_value=AsyncMock()),
        )
    )
    stack.enter_context(
        patch(
            "custom_components.motorola_nursery.async_setup_entry",
            AsyncMock(return_value=True),
        )
    )
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["errors"] == {"base": "pairing_not_ready"}
    probe.assert_not_called()
    enrollment.device = replace(enrollment.device, identifier="synthetic-id")
    enrollment.registered.set()
    next(iter(control._entries.values())).ready.set()
    if probe_failure:
        probe.side_effect = ConnectionRefusedError
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    if probe_failure:
        assert result["errors"] == {"base": "local_video_unavailable"}
        assert not hass.config_entries.async_entries(DOMAIN)
        assert enrollment.server is not None
        hass.config_entries.flow.async_abort(result["flow_id"])
    else:
        assert result["type"] == FlowResultType.CREATE_ENTRY
        data = result["data"]
        assert data["local_pairing"] and data["local_control"]
        assert data["sid_device"] == enrollment.device.sid_device
        assert set(data).isdisjoint({"ssid", "wifi_password", "cloud_session", "email"})
        assert SETTINGS["wifi_password"] not in str(data)
    await hass.async_block_till_done()
    assert_closed(clock, control, enrollment)


async def test_invalid_settings_do_not_open_a_listener(hass, pairing_resources):
    clock, control, enrollment, _ = pairing_resources
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "local_pairing"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**SETTINGS, "host": "8.8.8.8"}
    )
    assert result["errors"] == {"base": "invalid_pairing_settings"}
    assert_closed(clock, control, enrollment)
    hass.config_entries.flow.async_abort(result["flow_id"])
    await hass.async_block_till_done()


async def test_explicit_save_preserves_authenticated_pairing_after_video_failure(
    hass, pairing_resources
):
    clock, control, enrollment, stack = pairing_resources
    probe = stack.enter_context(
        patch(
            "custom_components.motorola_nursery.config_flow_local.MagicP2PTunnel.connect",
            AsyncMock(side_effect=ConnectionRefusedError),
        )
    )
    stack.enter_context(
        patch(
            "custom_components.motorola_nursery.async_setup_entry",
            AsyncMock(return_value=True),
        )
    )
    result = await start(hass)
    enrollment.registered.set()
    next(iter(control._entries.values())).ready.set()
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["errors"] == {"base": "local_video_unavailable"}
    assert not hass.config_entries.async_entries(DOMAIN)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"save_pairing": True}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["sid_user_id"] == enrollment.device.owner_id
    assert "cloud_session" not in result["data"]
    probe.assert_awaited_once()
    await hass.async_block_till_done()
    assert_closed(clock, control, enrollment)


async def test_expiry_during_video_probe_cannot_restore_qr_or_save_entry(
    hass, pairing_resources
):
    clock, control, enrollment, stack = pairing_resources
    result = await start(hass)
    flow = hass.config_entries.flow._progress[result["flow_id"]]
    selector = next(iter(result["data_schema"].schema.values()))
    enrollment.registered.set()
    next(iter(control._entries.values())).ready.set()

    async def expire_during_probe(*_):
        await flow._close_pairing()
        raise ConnectionRefusedError

    stack.enter_context(
        patch(
            "custom_components.motorola_nursery.config_flow_local.MagicP2PTunnel.connect",
            side_effect=expire_during_probe,
        )
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["reason"] == "pairing_expired"
    assert selector.config["data"] == ""
    assert not hass.config_entries.async_entries(DOMAIN)
    await hass.async_block_till_done()
    assert_closed(clock, control, enrollment)


@pytest.mark.parametrize(
    "finish",
    [
        "success",
        "abort",
        "expiry",
        "video_failure",
        "changed",
        "reconnect_without_enrollment",
        "unconfirmed_video_failure",
        "same_address",
        "no_reconnect",
    ],
)
async def test_wifi_change_preserves_entry_keys_and_live_registration(
    hass, pairing_resources, finish
):
    from unittest.mock import Mock

    from homeassistant import config_entries
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.motorola_nursery.auth import device_data

    clock, control, original, stack = pairing_resources
    initial = {
        **device_data(original.device),
        "host": "192.168.12.4",
        "local_server": SETTINGS["local_server"],
        "local_control": True,
        "local_pairing": True,
    }
    if finish == "same_address":
        initial["host"] = SETTINGS["host"]
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=original.device.sid_device,
        title="Existing camera",
        data=initial,
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    entity = registry.async_get_or_create(
        "camera",
        DOMAIN,
        entry.unique_id,
        config_entry=entry,
        suggested_object_id="existing_camera",
    )
    await clock.register(entry.entry_id, initial["host"])
    registration = await control.register(entry.entry_id, lambda: original.credentials)
    peer = Mock()
    peer.connection.writer.get_extra_info.return_value = (SETTINGS["host"], 1234)
    registration.peer = peer
    registration.ready.set()
    stack.enter_context(
        patch(
            "custom_components.motorola_nursery.config_flow_local.LocalEnrollment",
            side_effect=lambda address, **kw: LocalEnrollment(address, 0, **kw),
        )
    )
    probe = stack.enter_context(
        patch(
            "custom_components.motorola_nursery.config_flow_local.MagicP2PTunnel.connect",
            AsyncMock(return_value=AsyncMock()),
        )
    )
    stack.enter_context(
        patch(
            "custom_components.motorola_nursery.async_setup_entry",
            AsyncMock(return_value=True),
        )
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    assert "change_wifi" in result["menu_options"]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "change_wifi"}
    )
    if finish == "expiry":
        stack.enter_context(
            patch(
                "custom_components.motorola_nursery.config_flow_local.PAIRING_SECONDS",
                0.01,
            )
        )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], SETTINGS)
    flow = hass.config_entries.flow._progress[result["flow_id"]]
    enrollment = flow._pairing
    assert enrollment.credentials == original.credentials
    assert control.get_registration(entry.entry_id) is registration
    assert len(control._entries) == 1
    assert entry.data == initial
    without_enrollment = finish in {
        "reconnect_without_enrollment",
        "unconfirmed_video_failure",
        "same_address",
        "no_reconnect",
    }
    if not without_enrollment:
        enrollment.registered.set()
    elif finish != "no_reconnect":
        replacement = Mock()
        replacement.connection.writer.get_extra_info.return_value = (
            SETTINGS["host"],
            5678,
        )
        registration.peer = replacement
    if finish == "abort":
        hass.config_entries.flow.async_abort(result["flow_id"])
    elif finish == "expiry":
        await asyncio.sleep(0.03)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["reason"] == "pairing_expired"
    else:
        if finish in {"video_failure", "unconfirmed_video_failure"}:
            probe.side_effect = ConnectionRefusedError
        if finish == "changed":
            hass.config_entries.async_update_entry(
                entry, data={**initial, "local_server": "192.168.12.9"}
            )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        if finish in {
            "video_failure",
            "unconfirmed_video_failure",
            "same_address",
            "no_reconnect",
        }:
            expected_error = (
                "pairing_not_ready"
                if finish == "same_address"
                else "local_control_not_ready"
                if finish == "no_reconnect"
                else "local_video_unavailable"
            )
            assert result["errors"] == {"base": expected_error}
            if finish == "unconfirmed_video_failure":
                assert "save_pairing" not in [
                    k.schema for k in result["data_schema"].schema
                ]
            if finish in {"same_address", "no_reconnect"}:
                probe.assert_not_called()
            hass.config_entries.flow.async_abort(result["flow_id"])
        else:
            assert result["reason"] == (
                "pairing_configuration_changed"
                if finish == "changed"
                else "reconfigure_successful"
            )
    await hass.async_block_till_done()
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert entry.unique_id == original.device.sid_device
    assert registry.async_get(entity.entity_id).unique_id == entry.unique_id
    assert entry.data == (
        {**initial, "host": SETTINGS["host"]}
        if finish in {"success", "reconnect_without_enrollment"}
        else {**initial, "local_server": "192.168.12.9"}
        if finish == "changed"
        else initial
    )
    assert control.get_registration(entry.entry_id) is registration
    assert clock.peers == {entry.entry_id: initial["host"]}
    peer.close.assert_not_called()
    assert enrollment.server is None
    await control.unregister(entry.entry_id)
    await clock.unregister(entry.entry_id)


@pytest.mark.parametrize("old_address", [("192.168.12.4", 1234), None])
async def test_wifi_control_wait_rejects_old_peer_until_new_connection(
    hass, old_address
):
    from unittest.mock import Mock

    from custom_components.motorola_nursery.config_flow import ConfigFlow
    from custom_components.motorola_nursery.local import Registration

    flow = ConfigFlow()
    flow.hass = hass
    flow._wifi_target = Mock()
    registration = Registration(lambda: None)
    peer = Mock()
    peer.connection.writer.get_extra_info.return_value = old_address
    registration.peer = peer
    registration.ready.set()
    flow._pairing_registration = registration
    task = asyncio.create_task(
        flow._wait_for_pairing_control(Mock(peer=SETTINGS["host"]))
    )
    await asyncio.sleep(0)
    assert not task.done()
    peer.connection.writer.get_extra_info.return_value = (SETTINGS["host"], 5678)
    registration.connection_changed(True)
    await asyncio.wait_for(task, 1)
    assert not registration.connection_callbacks
