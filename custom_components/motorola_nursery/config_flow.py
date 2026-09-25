"""Email-code onboarding, account reauthentication, and host reconfiguration."""

from __future__ import annotations

import asyncio
import secrets
import string
from typing import Any, override

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.util.network import is_host_valid

from .auth import account_lock, async_client, credentials_from_data, device_data
from .cloud import (
    AuthenticationError,
    Challenge,
    CloudClient,
    CloudError,
    Device,
    Session,
    atom,
)
from .const import CONF_CODE, CONF_DEVICE, CONF_EMAIL, CONF_SESSION, DOMAIN
from .protocol import MagicP2PTunnel

NETWORK_ERRORS = (OSError, TimeoutError, EOFError)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """One config entry per camera, preserving the original unique ID."""

    VERSION = 1

    def __init__(self) -> None:
        self._client: CloudClient | None = None
        self._challenge: Challenge | None = None
        self._session: Session | None = None
        self._email = ""
        self._login_uuid = "".join(
            secrets.choice(string.ascii_uppercase + string.digits) for _ in range(32)
        )
        self._devices: dict[str, Device] = {}
        self._selected: Device | None = None
        self._expiry: asyncio.TimerHandle | None = None

    def _target_entry(self):
        if self.source == config_entries.SOURCE_REAUTH:
            return self._get_reauth_entry()
        if self.source == config_entries.SOURCE_RECONFIGURE:
            return self._get_reconfigure_entry()
        return None

    async def _close_client(self) -> None:
        if self._expiry is not None:
            self._expiry.cancel()
            self._expiry = None
        client, self._client = self._client, None
        if client is not None:
            await client.close()

    @callback
    @override
    def async_remove(self) -> None:
        super().async_remove()
        self.hass.async_create_task(self._close_client())

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """An explicit email form submission is the only code-send trigger."""
        errors = {}
        target = self._target_entry()
        default_email = self._email or (
            target.data.get(CONF_EMAIL, "") if target else ""
        )
        if user_input is not None:
            await self._close_client()
            self._challenge = None
            try:
                email = atom(user_input[CONF_EMAIL].strip())
                if email.count("@") != 1 or len(email) > 254:
                    raise ValueError("Invalid email")
                self._email = email
                self._client = await async_client(self.hass)
                await self._client.connect()
                self._challenge = await self._client.request_code(
                    self._login_uuid, email
                )
            except ValueError:
                errors[CONF_EMAIL] = "invalid_email"
            except NETWORK_ERRORS:
                errors["base"] = "cannot_connect_cloud"
            except CloudError:
                errors["base"] = "code_request_failed"
            else:
                self._expiry = self.hass.loop.call_later(
                    900, lambda: self.hass.async_create_task(self._close_client())
                )
                return await self.async_step_code()
            await self._close_client()
        return self.async_show_form(
            step_id="user",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL, default=default_email): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.EMAIL)
                    )
                }
            ),
        )

    async def async_step_code(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors = {}
        if self._client is None or self._challenge is None:
            return self.async_abort(reason="code_expired")
        if user_input is not None:
            try:
                if self._client.host != self._challenge.host:
                    await self._client.close()
                    self._client = await async_client(self.hass, self._challenge.host)
                    await self._client.connect()
                self._session = await self._client.submit_code(
                    self._challenge,
                    self._login_uuid,
                    self._email,
                    user_input[CONF_CODE].strip(),
                )
                # Do not request/submit the email code again if listing fails.
                return await self.async_step_devices()
            except (AuthenticationError, ValueError):
                errors[CONF_CODE] = "invalid_code"
            except NETWORK_ERRORS:
                await self._close_client()
                return self.async_abort(reason="login_connection_lost")
            except CloudError:
                errors["base"] = "cloud_error"
        return self.async_show_form(
            step_id="code",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CODE): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    )
                }
            ),
        )

    async def async_step_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Retry device listing without replaying a successful one-time code."""
        errors = {}
        try:
            if self._client is None:
                assert self._session is not None
                self._client = await async_client(self.hass, self._session.host)
                await self._client.connect()
                self._session = await self._client.resume(self._session)
            devices = await self._client.devices()
        except AuthenticationError:
            await self._close_client()
            return self.async_abort(reason="login_connection_lost")
        except (*NETWORK_ERRORS, CloudError):
            await self._close_client()
            errors["base"] = "cannot_connect_cloud"
        else:
            await self._close_client()
            self._devices = {device.sid_device: device for device in devices}
            target = self._target_entry()
            if target is not None:
                if target.unique_id not in self._devices:
                    return self.async_abort(reason="wrong_account")
                self._selected = self._devices[target.unique_id]
                return await self.async_step_host()
            if not self._devices:
                return self.async_abort(reason="no_devices")
            return await self.async_step_device()
        return self.async_show_form(
            step_id="devices", data_schema=vol.Schema({}), errors=errors
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            device = self._devices.get(user_input[CONF_DEVICE])
            if device is not None:
                await self.async_set_unique_id(device.sid_device)
                self._abort_if_unique_id_configured()
                self._selected = device
                return await self.async_step_host()
        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                {"value": value, "label": device.name}
                                for value, device in self._devices.items()
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_host(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._selected is not None and self._session is not None
        target = self._target_entry()
        previous = target.data if target else {}
        errors = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            if not is_host_valid(host):
                errors[CONF_HOST] = "invalid_host"
            else:
                data = {
                    **device_data(self._selected, previous),
                    CONF_HOST: host,
                    CONF_EMAIL: self._email,
                    CONF_SESSION: self._session.as_dict(),
                }
                try:
                    tunnel = await MagicP2PTunnel.connect(
                        host, credentials_from_data(data)
                    )
                    await tunnel.close()
                except NETWORK_ERRORS:
                    errors["base"] = "cannot_connect"
                except ValueError:
                    errors["base"] = "invalid_auth"
                else:
                    if target is not None:
                        async with account_lock(self.hass, target):
                            return self.async_update_reload_and_abort(
                                target, data_updates=data
                            )
                    return self.async_create_entry(title=self._selected.name, data=data)
        return self.async_show_form(
            step_id="host",
            errors=errors,
            data_schema=vol.Schema(
                {vol.Required(CONF_HOST, default=previous.get(CONF_HOST, "")): str}
            ),
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_user()

    async def async_step_reconfigure(self, user_input=None) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="reconfigure", menu_options=["user", "change_host"]
        )

    async def async_step_change_host(self, user_input=None) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            if not is_host_valid(host):
                errors[CONF_HOST] = "invalid_host"
            else:
                try:
                    tunnel = await MagicP2PTunnel.connect(
                        host, credentials_from_data(entry.data)
                    )
                    await tunnel.close()
                except NETWORK_ERRORS:
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_update_reload_and_abort(
                        entry, data_updates={CONF_HOST: host}
                    )
        return self.async_show_form(
            step_id="change_host",
            errors=errors,
            data_schema=vol.Schema(
                {vol.Required(CONF_HOST, default=entry.data[CONF_HOST]): str}
            ),
        )
