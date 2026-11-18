"""Setup: pick the EHC-16 module, type the PIN from its sticker, done."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .client import AuthError
from .catalog import DEFAULT_KEYS, EXTRAS
from .const import (
    CONF_EXTRAS,
    CONF_MODE,
    CONF_PIN,
    CONF_SERIAL,
    DOMAIN,
    MODE_ADVANCED,
    MODE_SIMPLE,
    NAME_PREFIX,
)
from .coordinator import CannotConnect, async_open_session
from .pairing import InvalidPin, PairingError

_LOGGER = logging.getLogger(__name__)

PIN_SCHEMA = vol.Schema({vol.Required(CONF_PIN): str})


def _clean_pin(pin: str) -> str:
    return "".join(c for c in pin if c.isdigit())


class RemehaConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> RemehaOptionsFlow:
        return RemehaOptionsFlow()

    def __init__(self) -> None:
        self._address: str | None = None
        self._name: str | None = None
        self._found: dict[str, str] = {}

    async def _try_pin(self, pin: str) -> str | None:
        """Connect, bond and read once. Returns an error key or None."""
        assert self._address
        if len(pin) != 6:
            return "pin_format"
        try:
            client, session = await async_open_session(self.hass, self._address, pin)
            try:
                await session.read_all()
            finally:
                await client.disconnect()
        except InvalidPin:
            return "invalid_pin"
        except (CannotConnect, PairingError):
            _LOGGER.exception("Could not connect/bond")
            return "cannot_connect"
        except AuthError:
            _LOGGER.exception("Handshake failed")
            return "auth_failed"
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error")
            return "cannot_connect"
        return None

    # -- discovered automatically -------------------------------------------
    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._address = discovery_info.address
        self._name = discovery_info.name
        self.context["title_placeholders"] = {"name": self._name}
        return await self.async_step_pin()

    # -- added by hand ------------------------------------------------------
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._address = user_input[CONF_ADDRESS]
            self._name = self._found.get(self._address, self._address)
            await self.async_set_unique_id(self._address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return await self.async_step_pin()

        configured = self._async_current_ids(include_ignore=False)
        for info in async_discovered_service_info(self.hass, connectable=True):
            if (info.name or "").startswith(NAME_PREFIX) and info.address not in configured:
                self._found[info.address] = f"{info.name} ({info.address})"
        if not self._found:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(self._found)}),
        )

    async def async_step_pin(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            pin = _clean_pin(user_input[CONF_PIN])
            if (err := await self._try_pin(pin)) is None:
                name = self._name or ""
                serial = name.split("_", 1)[1] if "_" in name else None
                return self.async_create_entry(
                    title="Heat pump",
                    data={CONF_ADDRESS: self._address, CONF_PIN: pin, CONF_SERIAL: serial},
                )
            errors["base"] = err
        return self.async_show_form(
            step_id="pin",
            data_schema=PIN_SCHEMA,
            errors=errors,
            description_placeholders={"name": self._name or ""},
        )


class RemehaOptionsFlow(OptionsFlowWithReload):
    """Simple = the standard sensors. Advanced = tick any datapoint from the list."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            if user_input[CONF_MODE] == MODE_ADVANCED:
                return await self.async_step_advanced()
            return self.async_create_entry(data={CONF_MODE: MODE_SIMPLE})
        mode = self.config_entry.options.get(CONF_MODE, MODE_SIMPLE)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_MODE, default=mode): SelectSelector(SelectSelectorConfig(
                    options=[MODE_SIMPLE, MODE_ADVANCED],
                    translation_key=CONF_MODE,
                    mode=SelectSelectorMode.LIST,
                )),
            }),
        )

    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None and CONF_EXTRAS in user_input:
            return self.async_create_entry(
                data={CONF_MODE: MODE_ADVANCED, CONF_EXTRAS: user_input[CONF_EXTRAS]}
            )
        chosen = self.config_entry.options.get(CONF_EXTRAS, DEFAULT_KEYS)
        return self.async_show_form(
            step_id="advanced",
            data_schema=vol.Schema({
                vol.Optional(CONF_EXTRAS, default=chosen): SelectSelector(SelectSelectorConfig(
                    options=[e.key for e in EXTRAS],
                    translation_key=CONF_EXTRAS,
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )),
            }),
        )
