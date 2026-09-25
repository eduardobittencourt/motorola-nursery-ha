"""Explicit allowlist: never export config entries, URLs, tokens or account IDs."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_SESSION


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    return {
        "entry_version": entry.version,
        "account_login_configured": CONF_SESSION in entry.data,
        "entry_state": entry.state.value,
    }
