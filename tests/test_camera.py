"""Still images reuse native stream frames even if WebRTC image capture fails."""

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.components.camera import _async_get_image
from homeassistant.components.camera.prefs import DynamicStreamSettings
from homeassistant.components.stream.core import IdleTimer
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.motorola_nursery.camera import MotorolaNurseryCamera
from custom_components.motorola_nursery.const import DOMAIN


def camera_with_runtime(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="synthetic-camera",
        title="Synthetic camera",
        data={"model": "VM65CONNECT"},
    )
    runtime = SimpleNamespace(
        async_prepare_stream=AsyncMock(),
        relay=SimpleNamespace(url="http://127.0.0.1:12345/synthetic.ts"),
    )
    entry.runtime_data = runtime
    camera = MotorolaNurseryCamera(entry)
    camera.hass = hass
    camera.entity_id = "camera.synthetic_camera"
    return camera


@pytest.mark.parametrize("stream_already_running", [False, True])
async def test_snapshot_uses_native_frames_when_webrtc_capture_fails(
    hass, stream_already_running
):
    camera = camera_with_runtime(hass)
    stream = Mock(
        async_get_image=AsyncMock(return_value=b"synthetic-jpeg"), available=True
    )
    provider = Mock(
        async_get_image=AsyncMock(side_effect=RuntimeError("WebRTC capture failed"))
    )
    camera._webrtc_provider = provider
    if stream_already_running:
        camera.stream = stream

    with (
        patch(
            "homeassistant.components.camera.create_stream", return_value=stream
        ) as create,
        patch(
            "homeassistant.components.camera.get_dynamic_camera_stream_settings",
            AsyncMock(return_value=DynamicStreamSettings()),
        ),
    ):
        first = await _async_get_image(camera)
        second = await _async_get_image(camera)

    assert first.content == second.content == b"synthetic-jpeg"
    assert camera.stream is stream
    assert create.call_count == (0 if stream_already_running else 1)
    assert stream.async_get_image.await_count == 2
    stream.async_get_image.assert_awaited_with(
        width=None, height=None, wait_for_next_keyframe=True
    )
    provider.async_get_image.assert_not_awaited()


async def test_snapshot_cancellation_releases_pending_frame_request(hass):
    camera = camera_with_runtime(hass)
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def frame(**kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    camera.stream = Mock(async_get_image=AsyncMock(side_effect=frame), available=True)
    task = asyncio.create_task(camera.async_camera_image())
    await asyncio.wait_for(started.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled.is_set()


async def test_snapshot_discards_buffered_frame_when_stream_disconnects(hass):
    camera = camera_with_runtime(hass)

    async def disconnected_frame(**kwargs):
        stream.available = False
        return b"buffered-jpeg"

    stream = Mock(
        async_get_image=AsyncMock(side_effect=disconnected_frame), available=True
    )
    camera.stream = stream

    assert await camera.async_camera_image() is None


async def test_active_snapshots_keep_worker_alive_then_release_when_idle(hass, freezer):
    camera = camera_with_runtime(hass)
    expired = asyncio.Event()

    async def idle():
        expired.set()

    timer = IdleTimer(hass, 30, idle, startup_timeout=60)
    timer.start()
    camera.stream = Mock(
        async_get_image=AsyncMock(return_value=b"synthetic-jpeg"),
        add_provider=Mock(return_value=SimpleNamespace(idle_timer=timer)),
        available=True,
    )
    try:
        for _ in range(4):
            assert await camera.async_camera_image() == b"synthetic-jpeg"
            freezer.tick(timedelta(seconds=20))
            async_fire_time_changed(hass, dt_util.utcnow())
            await hass.async_block_till_done()
            assert not expired.is_set()

        freezer.tick(timedelta(seconds=31))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()
        assert expired.is_set()
    finally:
        timer.clear()
