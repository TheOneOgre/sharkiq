"""Config flow for Shark IQ integration."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_REGION, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .const import (
    DOMAIN,
    LOGGER,
    SHARKIQ_REGION_DEFAULT,
    SHARKIQ_REGION_EUROPE,
    SHARKIQ_REGION_OPTIONS,
    AUTH0_REFRESH_TOKEN_KEY,
)
from .sharkiq import SharkIqAuthError, get_ayla_api

UI_FIELD_EMAIL = "Username"
UI_FIELD_PASSWORD = "Password"

SHARKIQ_SCHEMA = vol.Schema(
    {
        vol.Required(UI_FIELD_EMAIL): str,
        vol.Required(UI_FIELD_PASSWORD): str,
        vol.Required(
            CONF_REGION, default=SHARKIQ_REGION_DEFAULT
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=SHARKIQ_REGION_OPTIONS, translation_key="region"
            ),
        ),
        vol.Optional("force_interactive_debug", default=False): bool,
    }
)


async def _validate_input(
    hass: HomeAssistant, data: Mapping[str, Any]
) -> dict[str, str]:
    """Validate the user input allows us to connect."""
    new_websession = async_create_clientsession(
        hass,
        cookie_jar=aiohttp.CookieJar(unsafe=True, quote_cookie=False),
    )
    ayla_api = get_ayla_api(
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
        websession=new_websession,
        europe=(data[CONF_REGION] == SHARKIQ_REGION_EUROPE),
        auth0_refresh_token=data.get(AUTH0_REFRESH_TOKEN_KEY),
    )

    if data.get("force_interactive_debug"):
        if not hasattr(ayla_api, "start_interactive_login"):
            raise UnknownAuth("Interactive auth not supported by current sharkiq library version")
        auth_flow = ayla_api.start_interactive_login()
        raise InteractiveAuth(auth_flow)

    try:
        async with asyncio.timeout(15):
            LOGGER.debug("Initialize connection to Ayla networks API")
            await ayla_api.async_sign_in()
    except (TimeoutError, aiohttp.ClientError, TypeError) as error:
        LOGGER.error(error)
        raise CannotConnect(
            "Unable to connect to SharkIQ services.  Check your region settings."
        ) from error
    except SharkIqAuthError as error:
        LOGGER.error(error)
        if getattr(ayla_api, "requires_interactive_login", False):
            if not hasattr(ayla_api, "start_interactive_login"):
                raise UnknownAuth("Interactive auth not supported by current sharkiq library version") from error
            # Build interactive Auth0 URL (PKCE) for the user to complete the verification.
            auth_flow = ayla_api.start_interactive_login()
            raise InteractiveAuth(auth_flow) from error
        raise InvalidAuth(
            "Username or password incorrect.  Please check your credentials."
        ) from error
    except Exception as error:
        LOGGER.exception("Unexpected exception")
        LOGGER.error(error)
        raise UnknownAuth(
            "An unknown error occurred. Check your region settings and open an issue on Github if the issue persists."
        ) from error

    entry = {"title": data[CONF_USERNAME]}
    if getattr(ayla_api, "auth0_refresh_token", None):
        entry[AUTH0_REFRESH_TOKEN_KEY] = ayla_api.auth0_refresh_token
    return entry


class SharkIqConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Shark IQ."""

    VERSION = 1

    def __init__(self) -> None:
        self._pending_auth_flow: dict[str, Any] | None = None
        self._pending_user_input: Mapping[str, Any] | None = None

    async def _async_validate_input(
        self, user_input: Mapping[str, Any]
    ) -> tuple[dict[str, str] | None, dict[str, str]]:
        """Validate form input."""
        normalized_input: dict[str, Any] = {
            CONF_USERNAME: user_input[UI_FIELD_EMAIL],
            CONF_PASSWORD: user_input[UI_FIELD_PASSWORD],
            CONF_REGION: user_input[CONF_REGION],
            "force_interactive_debug": user_input.get("force_interactive_debug", False),
        }
        errors = {}
        info = None
        # Store normalized copy so we can drop debug-only fields later.
        self._pending_user_input = dict(normalized_input)

        # noinspection PyBroadException
        try:
            info = await _validate_input(self.hass, normalized_input)
            self._pending_auth_flow = None
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except InteractiveAuth as interactive:
            # Store interactive auth details and move to next step.
            self._pending_auth_flow = interactive.auth_flow
            errors["base"] = "interactive_required"
        except UnknownAuth:
            errors["base"] = "unknown"
        return info, errors

    async def async_step_user(
        self, user_input: dict[str, str] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            info, errors = await self._async_validate_input(user_input)
            if info:
                await self.async_set_unique_id(self._pending_user_input[CONF_USERNAME])
                self._abort_if_unique_id_configured()
                data = dict(self._pending_user_input)
                # Persist any refresh token collected during validation.
                rt = info.get(AUTH0_REFRESH_TOKEN_KEY)
                if rt:
                    data[AUTH0_REFRESH_TOKEN_KEY] = rt
                data.pop("force_interactive_debug", None)
                return self.async_create_entry(title=info["title"], data=data)
            if errors.get("base") == "interactive_required" and self._pending_auth_flow:
                # Hand off to the interactive step so we only render one form.
                return await self.async_step_interactive()

        return self.async_show_form(
            step_id="user", data_schema=SHARKIQ_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-auth if login is invalid."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initiated by reauthentication."""
        errors: dict[str, str] = {}

        if user_input is not None:
            _, errors = await self._async_validate_input(user_input)

            if not errors:
                errors = {"base": "unknown"}
                if entry := await self.async_set_unique_id(self.unique_id):
                    data = dict(self._pending_user_input)
                    rt = data.get(AUTH0_REFRESH_TOKEN_KEY)
                    if rt:
                        data[AUTH0_REFRESH_TOKEN_KEY] = rt
                    data.pop("force_interactive_debug", None)
                    self.hass.config_entries.async_update_entry(entry, data=data)
                    return self.async_abort(reason="reauth_successful")

            if errors["base"] != "invalid_auth":
                return self.async_abort(reason=errors["base"])

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=SHARKIQ_SCHEMA,
            errors=errors,
        )

    async def async_step_interactive(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle interactive Auth0 verification."""
        if not self._pending_auth_flow or not self._pending_user_input:
            return self.async_abort(reason="unknown")

        errors: dict[str, str] = {}
        auth_url = self._pending_auth_flow.get("url", "")
        auth_label = auth_url or "Auth link unavailable. Go back and retry."

        if user_input is not None:
            redirect_url = (user_input.get("redirect_url") or "").strip()

            code = None
            if redirect_url:
                # Expect full redirect URL; extract ?code=...&state=...
                parsed = aiohttp.helpers.URL(redirect_url)
                code = parsed.query.get("code")
                # Ignore state mismatch to avoid false expirations; code is sufficient.

            if code and not errors:
                # Recreate Ayla API with stored creds and complete interactive login.
                new_websession = async_create_clientsession(
                    self.hass,
                    cookie_jar=aiohttp.CookieJar(unsafe=True, quote_cookie=False),
                )
                ayla_api = get_ayla_api(
                    username=self._pending_user_input[CONF_USERNAME],
                    password=self._pending_user_input[CONF_PASSWORD],
                    websession=new_websession,
                    europe=(self._pending_user_input[CONF_REGION] == SHARKIQ_REGION_EUROPE),
                )
                try:
                    async with asyncio.timeout(15):
                        await ayla_api.complete_interactive_login(
                            code,
                            code_verifier=self._pending_auth_flow.get("code_verifier"),
                        )
                except (TimeoutError, aiohttp.ClientError, TypeError) as error:
                    LOGGER.error(error)
                    errors["base"] = "cannot_connect"
                except SharkIqAuthError as error:
                    LOGGER.error(error)
                    errors["base"] = "invalid_code"
                except Exception as error:
                    LOGGER.exception("Unexpected exception during interactive auth")
                    LOGGER.error(error)
                    errors["base"] = "unknown"

                if not errors:
                    await self.async_set_unique_id(self._pending_user_input[CONF_USERNAME])
                    self._abort_if_unique_id_configured()
                    data = dict(self._pending_user_input)
                    rt = getattr(ayla_api, "auth0_refresh_token", None)
                    if rt:
                        data[AUTH0_REFRESH_TOKEN_KEY] = rt
                    data.pop("force_interactive_debug", None)
                    return self.async_create_entry(
                        title=self._pending_user_input[CONF_USERNAME], data=data
                    )
            elif not errors:
                errors["base"] = "missing_token"

        return self.async_show_form(
            step_id="interactive",
            data_schema=vol.Schema(
                {
                    vol.Required("redirect_url"): str,
                }
            ),
            description_placeholders={
                "auth_url": auth_url or "#",
                "auth_label": auth_label,
                "state": self._pending_auth_flow.get("state", ""),
            },
            errors=errors,
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class UnknownAuth(HomeAssistantError):
    """Error to indicate there is an uncaught auth error."""


class InteractiveAuth(HomeAssistantError):
    """Error to indicate interactive Auth0 verification is required."""

    def __init__(self, auth_flow: dict[str, Any]) -> None:
        super().__init__("Interactive authentication required")
        self.auth_flow = auth_flow
