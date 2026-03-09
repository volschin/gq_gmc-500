"""Config flow for GQ GMC-500 integration."""

from __future__ import annotations

import socket
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback

from .const import DOMAIN, DEFAULT_PORT, CONF_PORT, CONF_IGNORED_DEVICES

_LOGGER = logging.getLogger(__name__)


def test_port_available(port: int) -> bool:
    """Test if a TCP port is available."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        sock.bind(("0.0.0.0", port))
        sock.close()
        return True
    except OSError:
        return False


class GMC500ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for GMC-500."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow."""
        self._discovery_data: dict[str, Any] | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            port = user_input[CONF_PORT]
            available = await self.hass.async_add_executor_job(
                test_port_available, port
            )
            if not available:
                errors[CONF_PORT] = "port_in_use"
            else:
                return self.async_create_entry(
                    title="GQ GMC-500",
                    data={CONF_PORT: port},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
                        int, vol.Range(min=1024, max=65535)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_discovery(
        self, discovery_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle device discovery."""
        self._discovery_data = discovery_data
        aid = discovery_data["aid"]
        gid = discovery_data["gid"]
        await self.async_set_unique_id(f"{aid}_{gid}")
        self._abort_if_unique_id_configured()
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle user confirmation of discovered device."""
        if user_input is not None:
            return self.async_create_entry(
                title=user_input.get("name", f"GMC-500 {self._discovery_data['gid']}"),
                data=self._discovery_data,
            )

        return self.async_show_form(
            step_id="discovery_confirm",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "name",
                        default=f"GMC-500 {self._discovery_data['gid']}",
                    ): str,
                }
            ),
            description_placeholders={
                "aid": self._discovery_data["aid"],
                "gid": self._discovery_data["gid"],
                "cpm": str(self._discovery_data.get("cpm", "N/A")),
            },
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of the integration."""
        errors: dict[str, str] = {}
        reconfigure_entry = self._get_reconfigure_entry()

        if user_input is not None:
            port = user_input[CONF_PORT]
            available = await self.hass.async_add_executor_job(
                test_port_available, port
            )
            if not available:
                errors[CONF_PORT] = "port_in_use"
            else:
                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    data_updates={CONF_PORT: port},
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_PORT,
                        default=reconfigure_entry.data.get(CONF_PORT, DEFAULT_PORT),
                    ): vol.All(int, vol.Range(min=1024, max=65535)),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get options flow handler."""
        return GMC500OptionsFlow(config_entry)


class GMC500OptionsFlow(OptionsFlow):
    """Handle options flow for GMC-500."""

    def __init__(self, config_entry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            port = user_input[CONF_PORT]
            current_port = self.config_entry.data.get(CONF_PORT, DEFAULT_PORT)
            if port != current_port:
                available = await self.hass.async_add_executor_job(
                    test_port_available, port
                )
                if not available:
                    errors[CONF_PORT] = "port_in_use"
            if not errors:
                return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_PORT,
                        default=self.config_entry.options.get(
                            CONF_PORT,
                            self.config_entry.data.get(CONF_PORT, DEFAULT_PORT),
                        ),
                    ): vol.All(int, vol.Range(min=1024, max=65535)),
                }
            ),
            errors=errors,
        )
