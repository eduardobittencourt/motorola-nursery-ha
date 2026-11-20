"""Experimental QR provisioning using only the active HA configuration flow."""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import quote

import voluptuous as vol
from homeassistant.const import CONF_HOST
from homeassistant.helpers.selector import (
    QrCodeSelector,
    QrCodeSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .auth import credentials_from_data, device_data
from .bootstrap import (
    PAIRING_SECONDS,
    LocalClockServer,
    LocalEnrollment,
    LocalHttpDnsServer,
    lan_address,
)
from .cloud import Device
from .const import CONF_LOCAL_CONTROL, CONF_LOCAL_PAIRING, DOMAIN
from .local import LocalControlServer
from .protocol import MagicP2PTunnel

_LOGGER = logging.getLogger(__name__)


class LocalPairingFlow:
    """Limit the enrollment window and discard Wi-Fi data after confirmation."""

    _pairing: LocalEnrollment | None = None
    _pairing_registration = None
    _pairing_expiry: asyncio.TimerHandle | None = None
    _pairing_key: str | None = None
    _pairing_qr = ""
    _pairing_selector: QrCodeSelector | None = None
    _pairing_server = ""
    _local_video_failed = False
    _wifi_target = None
    _wifi_entry_data = None
    _wifi_initial_peer = None

    async def _close_pairing(self) -> None:
        if self._pairing_expiry:
            self._pairing_expiry.cancel()
            self._pairing_expiry = None
        pairing, self._pairing = self._pairing, None
        self._pairing_qr = ""
        if self._pairing_selector is not None:
            self._pairing_selector.config["data"] = ""
            self._pairing_selector = None
        self._local_video_failed = False
        self._pairing_registration = None
        self._wifi_initial_peer = None
        if pairing:
            await pairing.stop()
        if self._pairing_key:
            key, self._pairing_key = self._pairing_key, None
            data = self.hass.data.get(DOMAIN, {})
            if "local_control_server" in data:
                await data["local_control_server"].unregister(key)
            if "local_clock_server" in data:
                await data["local_clock_server"].unregister(key)
            if "local_httpdns_server" in data:
                await data["local_httpdns_server"].unregister(key)

    async def async_step_change_wifi(self, user_input=None):
        target = self._get_reconfigure_entry()
        if not target.data.get(CONF_LOCAL_PAIRING, False):
            return self.async_abort(reason="local_pairing_required")
        self._wifi_target = target
        return await self.async_step_local_pairing(user_input)

    async def _wait_for_pairing_control(self, pairing):
        registration = self._pairing_registration
        changed = asyncio.Event()

        def connection_changed(_connected):
            changed.set()

        registration.connection_callbacks.add(connection_changed)
        try:
            async with asyncio.timeout(5):
                while True:
                    changed.clear()
                    await registration.ready.wait()
                    peer = registration.peer
                    address = (
                        peer.connection.writer.get_extra_info("peername")
                        if peer is not None
                        else None
                    )
                    if self._wifi_target is None or (
                        address is not None
                        and address[0] == pairing.peer
                        and (
                            pairing.registered.is_set()
                            or peer is not self._wifi_initial_peer
                        )
                    ):
                        return
                    await changed.wait()
        finally:
            registration.connection_callbacks.discard(connection_changed)

    async def async_step_local_pairing(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                peer = lan_address(user_input[CONF_HOST])
                server = lan_address(user_input["local_server"])
                if peer == server:
                    raise ValueError("Separate camera and HA addresses required")
                if self._wifi_target is None:
                    pairing = LocalEnrollment(peer)
                else:
                    target = self._wifi_target
                    credentials = credentials_from_data(target.data)
                    device = Device(
                        str(credentials.sid_user_id),
                        "pending",
                        target.data["model"],
                        quote(target.title, safe=""),
                        credentials.magic_token.decode(),
                        credentials.sid_device.decode(),
                        "-1",
                    )
                    pairing = LocalEnrollment(
                        peer, device=device, credentials=credentials
                    )
                qr = pairing.qr(user_input["ssid"], user_input["wifi_password"], server)
            except (ValueError, UnicodeError):
                errors["base"] = "invalid_pairing_settings"
            else:
                await self._close_pairing()
                self._pairing = pairing
                self._pairing_server = server
                self._pairing_key = "pairing_" + self.flow_id
                data = self.hass.data.setdefault(DOMAIN, {})
                control = data.setdefault("local_control_server", LocalControlServer())
                clock = data.setdefault("local_clock_server", LocalClockServer())
                httpdns = data.setdefault("local_httpdns_server", LocalHttpDnsServer())
                try:
                    await clock.register(self._pairing_key, peer)
                    await httpdns.register(self._pairing_key, peer, server)
                    if self._wifi_target is None:
                        self._pairing_registration = await control.register(
                            self._pairing_key, lambda: pairing.credentials
                        )
                    else:
                        self._pairing_registration = control.get_registration(
                            self._wifi_target.entry_id
                        )
                        if self._pairing_registration is None:
                            await self._close_pairing()
                            errors["base"] = "local_entry_unavailable"
                            return self._show_pairing_settings(errors)
                        self._wifi_entry_data = dict(self._wifi_target.data)
                        self._wifi_initial_peer = self._pairing_registration.peer
                    await pairing.start()
                except OSError:
                    await self._close_pairing()
                    errors["base"] = "pairing_ports_unavailable"
                else:
                    self._pairing_qr = qr
                    self._pairing_selector = QrCodeSelector(
                        QrCodeSelectorConfig(data=qr, scale=6)
                    )
                    self._pairing_expiry = self.hass.loop.call_later(
                        PAIRING_SECONDS,
                        lambda: self.hass.async_create_task(self._close_pairing()),
                    )
                    return await self.async_step_local_scan()
        return self._show_pairing_settings(errors)

    def _show_pairing_settings(self, errors):
        target = self._wifi_target
        host = vol.Required(CONF_HOST)
        server = vol.Required("local_server")
        if target is not None:
            server = vol.Required("local_server", default=target.data["local_server"])
        return self.async_show_form(
            step_id="change_wifi" if target is not None else "local_pairing",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required("ssid"): str,
                    vol.Required("wifi_password"): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    host: str,
                    server: str,
                }
            ),
        )

    async def async_step_local_scan(self, user_input=None):
        pairing = self._pairing
        if pairing is None:
            return self.async_abort(reason="pairing_expired")
        errors = {}
        if user_input is not None:
            changed_address = (
                self._wifi_target is not None
                and self._wifi_entry_data is not None
                and pairing.peer != self._wifi_entry_data[CONF_HOST]
            )
            if not pairing.registered.is_set() and not changed_address:
                errors["base"] = "pairing_not_ready"
            else:
                try:
                    await self._wait_for_pairing_control(pairing)
                except OSError:
                    errors["base"] = "local_control_not_ready"
                else:
                    save_pending = (
                        pairing.registered.is_set()
                        and self._local_video_failed
                        and user_input.get("save_pairing", False)
                    )
                    if not save_pending:
                        try:
                            tunnel = await MagicP2PTunnel.connect(
                                pairing.peer, pairing.credentials
                            )
                            await tunnel.close()
                        except (OSError, EOFError):
                            self._local_video_failed = True
                            errors["base"] = "local_video_unavailable"
                            _LOGGER.debug(
                                "Local pairing validation deferred: stage=video"
                            )
                    if not errors:
                        if self._pairing is not pairing:
                            return self.async_abort(reason="pairing_expired")
                        if self._wifi_target is not None:
                            target = self._wifi_target
                            if target.data != self._wifi_entry_data:
                                await self._close_pairing()
                                return self.async_abort(
                                    reason="pairing_configuration_changed"
                                )
                            _LOGGER.debug(
                                "Local Wi-Fi migration verified: enrollment_ack=%s",
                                pairing.registered.is_set(),
                            )
                            updates = {
                                CONF_HOST: pairing.peer,
                                "local_server": self._pairing_server,
                            }
                            await self._close_pairing()
                            return self.async_update_reload_and_abort(
                                target, data_updates=updates
                            )
                        device = pairing.device
                        data = {
                            **device_data(device),
                            CONF_HOST: pairing.peer,
                            CONF_LOCAL_CONTROL: True,
                            CONF_LOCAL_PAIRING: True,
                            "local_server": self._pairing_server,
                        }
                        await self.async_set_unique_id(device.sid_device)
                        self._abort_if_unique_id_configured()
                        await self._close_pairing()
                        return self.async_create_entry(title=device.name, data=data)
        if self._pairing is not pairing:
            return self.async_abort(reason="pairing_expired")
        fields = {
            vol.Optional("qr_code"): self._pairing_selector,
        }
        if self._local_video_failed and pairing.registered.is_set():
            fields[vol.Optional("save_pairing", default=False)] = bool
        return self.async_show_form(
            step_id="local_scan",
            errors=errors,
            data_schema=vol.Schema(fields),
        )
