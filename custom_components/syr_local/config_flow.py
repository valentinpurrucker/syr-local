"""Config flow for SYR Local: manual setup, Supervisor discovery, reconfigure."""

from __future__ import annotations

import logging
from typing import Any

import probatio

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector
from homeassistant.helpers.service_info.hassio import HassioServiceInfo

from .api import CannotConnectError, SyrLocalClient
from .const import DEFAULT_HOST, DEFAULT_PORT, DOMAIN
from .models import InvalidStateError, SyrLocalState, UnsupportedVersionError

_LOGGER = logging.getLogger(__name__)

CONNECTION_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_HOST, default=DEFAULT_HOST): TextSelector(),
        probatio.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
    }
)


class SyrLocalConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SYR Local."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, Any] = {}
        self._discovered_title = "SYR Local"

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _connection(user_input)
            state, error = await self._async_probe(data)
            if state is not None and state.device.serial:
                await self.async_set_unique_id(state.device.serial)
                self._abort_if_unique_id_configured(updates=data)
                return self.async_create_entry(title=_title(state), data=data)
            errors["base"] = error or "no_device"
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(CONNECTION_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_hassio(
        self, discovery_info: HassioServiceInfo
    ) -> ConfigFlowResult:
        """Handle discovery from the SYR Local add-on."""
        config = discovery_info.config
        host, port, serial = config.get(CONF_HOST), config.get(CONF_PORT), config.get("serial")
        if (
            not isinstance(host, str)
            or not host
            or isinstance(port, bool)
            or not isinstance(port, int)
            or not 0 < port < 65536
        ):
            return self.async_abort(reason="invalid_discovery_info")
        data = {CONF_HOST: host, CONF_PORT: port}
        if isinstance(serial, str) and serial:
            await self.async_set_unique_id(serial)
            self._abort_if_unique_id_configured(updates=data)

        state, error = await self._async_probe(data)
        if state is None:
            return self.async_abort(reason=error or "cannot_connect")
        if not state.device.serial:
            return self.async_abort(reason="no_device")
        await self.async_set_unique_id(state.device.serial)
        self._abort_if_unique_id_configured(updates=data)

        self._discovered = data
        self._discovered_title = _title(state)
        self.context["title_placeholders"] = {"name": self._discovered_title}
        return await self.async_step_hassio_confirm()

    async def async_step_hassio_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title=self._discovered_title, data=self._discovered)
        return self.async_show_form(
            step_id="hassio_confirm",
            description_placeholders={
                "name": self._discovered_title,
                "serial": self.unique_id or "",
            },
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _connection(user_input)
            state, error = await self._async_probe(data)
            if state is not None and state.device.serial:
                await self.async_set_unique_id(state.device.serial)
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(entry, data_updates=data)
            errors["base"] = error or "no_device"
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                CONNECTION_SCHEMA, user_input or entry.data
            ),
            errors=errors,
        )

    async def _async_probe(
        self, data: dict[str, Any]
    ) -> tuple[SyrLocalState | None, str | None]:
        """Fetch the state once; return it or a translation key for the error."""
        client = SyrLocalClient(
            async_get_clientsession(self.hass), data[CONF_HOST], data[CONF_PORT]
        )
        try:
            return await client.async_get_state(), None
        except CannotConnectError:
            return None, "cannot_connect"
        except UnsupportedVersionError:
            return None, "unsupported_version"
        except InvalidStateError:
            return None, "invalid_response"


def _connection(user_input: dict[str, Any]) -> dict[str, Any]:
    return {CONF_HOST: user_input[CONF_HOST].strip(), CONF_PORT: int(user_input[CONF_PORT])}


def _title(state: SyrLocalState) -> str:
    return f"SYR {state.device.model}" if state.device.model else "SYR Local"
