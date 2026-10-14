"""Explicit allowlist: never export config entries, URLs, tokens or account IDs."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_SESSION


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    runtime = getattr(entry, "runtime_data", None)
    coordinator = getattr(runtime, "telemetry", None)
    events = getattr(runtime, "events", None)
    initial_refresh = getattr(runtime, "telemetry_task", None)
    return {
        "entry_version": entry.version,
        "account_login_configured": CONF_SESSION in entry.data,
        "entry_state": entry.state.value,
        "telemetry_configured": coordinator is not None,
        "telemetry_available": bool(coordinator and coordinator.last_update_success),
        "telemetry_capability_count": (
            len(coordinator.data.capabilities)
            if coordinator and coordinator.data
            else 0
        ),
        "initial_telemetry_pending": bool(
            initial_refresh and not initial_refresh.done()
        ),
        "event_channel_connected": bool(events and events.connected),
        "local_bridge_connections": (
            runtime.bridge.active_connections if runtime else 0
        ),
        "active_video_processes": runtime.relay.active_processes if runtime else 0,
    }
