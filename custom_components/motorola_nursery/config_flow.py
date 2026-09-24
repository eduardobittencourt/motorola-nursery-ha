"""Config flow for Motorola Nursery Local."""

from __future__ import annotations

from typing import Any, override

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import voluptuous as vol

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_MAGIC_TOKEN,
    CONF_RTSP_PASSWORD,
    CONF_RTSP_USERNAME,
    CONF_SID_DEVICE,
    CONF_SID_USER_ID,
    DOMAIN,
)
from .protocol import Credentials, MagicP2PTunnel

SECRET = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Return the temporary expert credential schema."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
            vol.Required(
                CONF_SID_USER_ID, default=defaults.get(CONF_SID_USER_ID, "")
            ): str,
            vol.Required(
                CONF_SID_DEVICE, default=defaults.get(CONF_SID_DEVICE, "")
            ): SECRET,
            vol.Required(
                CONF_MAGIC_TOKEN, default=defaults.get(CONF_MAGIC_TOKEN, "")
            ): SECRET,
            vol.Required(
                CONF_RTSP_USERNAME, default=defaults.get(CONF_RTSP_USERNAME, "")
            ): str,
            vol.Required(
                CONF_RTSP_PASSWORD, default=defaults.get(CONF_RTSP_PASSWORD, "")
            ): SECRET,
            vol.Required(
                CONF_ACCESS_TOKEN, default=defaults.get(CONF_ACCESS_TOKEN, "")
            ): SECRET,
        }
    )


def credentials_from_input(data: dict[str, Any]) -> Credentials:
    """Parse technical credentials supplied by the setup flow."""
    return Credentials(
        sid_user_id=int(data[CONF_SID_USER_ID]),
        sid_device=data[CONF_SID_DEVICE].encode(),
        magic_token=data[CONF_MAGIC_TOKEN].encode(),
        rtsp_username=data[CONF_RTSP_USERNAME],
        rtsp_password=data[CONF_RTSP_PASSWORD],
        access_token=data[CONF_ACCESS_TOKEN],
    )


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure a Motorola Nursery camera."""

    VERSION = 1

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the temporary expert setup form."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                credentials = credentials_from_input(user_input)
                credentials.validate()
                tunnel = await MagicP2PTunnel.connect(
                    user_input[CONF_HOST], credentials
                )
                await tunnel.close()
            except (ConnectionError, OSError, TimeoutError):
                errors["base"] = "cannot_connect"
            except (KeyError, UnicodeError, ValueError):
                errors["base"] = "invalid_auth"
            else:
                await self.async_set_unique_id(credentials.sid_device.decode())
                self._abort_if_unique_id_configured(updates=user_input)
                return self.async_create_entry(
                    title="Motorola VM65 (integration)", data=user_input
                )

        return self.async_show_form(
            step_id="user",
            data_schema=schema(user_input),
            errors=errors,
        )
