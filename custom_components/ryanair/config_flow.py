"""Config flow for Ryanair integration."""

from __future__ import annotations

import hashlib
from typing import Any
import uuid

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CODE_MFA_CODE_WRONG,
    CODE_PASSWORD_WRONG,
    CODE_UNKNOWN_DEVICE,
    CONF_DEVICE_FINGERPRINT,
    CUSTOMER_ID,
    CUSTOMERS,
    DOMAIN,
    MFA_CODE,
    MFA_TOKEN,
    TOKEN,
)
from .coordinator import RyanairCoordinator, RyanairMfaCoordinator
from .errors import CannotConnect

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)
STEP_MFA = vol.Schema(
    {
        vol.Required(MFA_CODE): str,
    }
)


def generate_device_fingerprint(email: str) -> str:
    """Generate Device Fingerprint."""
    unique_id = hashlib.md5(email.encode("UTF-8")).hexdigest()
    return str(uuid.UUID(hex=unique_id))


async def validate_input(
    hass: HomeAssistant, data: dict[str, Any], fingerprint: str
) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    session = async_get_clientsession(hass)
    coordinator = RyanairCoordinator(hass, session, data, fingerprint)

    await coordinator.async_refresh()

    if coordinator.last_exception is not None:
        raise coordinator.last_exception

    body = coordinator.data

    err = None
    responseData = None
    if "code" in body:
        # Password is wrong, so display message.
        # {"code": "Mfa.Wrong.Code","message": "Mfa wrong code", "additionalData": [{"code": "Mfa.Available.Attempts","message": "4"}]}
        if body["code"] == CODE_PASSWORD_WRONG:
            err = (
                body["message"]
                + " "
                + body["additionalData"][0]["message"]
                + " retries remaining"
            )
        # New device, begin MFA process
        # {'code': 'Account.UnknownDeviceFingerprint', 'message': 'Unknown device fingerprint', 'additionalData': [{'code': 'Mfa.Token', 'message': '<MFA_TOKEN>'}]}
        if body["code"] == CODE_UNKNOWN_DEVICE:
            responseData = {MFA_TOKEN: body["additionalData"][0]["message"]}
    # Successful Login
    # {"customerId": "<CUSTOMER_ID>","token": "<ACCESS_TOKEN>"}
    if CUSTOMER_ID in body:
        responseData = {CUSTOMER_ID: body[CUSTOMER_ID], TOKEN: body[TOKEN]}

    # Return info that you want to store in the config entry.
    return {"title": str(data[CONF_EMAIL]), "data": responseData, "error": err}


async def validate_mfa_input(
    hass: HomeAssistant, data: dict[str, Any]
) -> dict[str, Any]:
    """Validate the MFA input allows us to connect."""

    session = async_get_clientsession(hass)
    coordinator = RyanairMfaCoordinator(hass, session, data)

    await coordinator.async_refresh()

    if coordinator.last_exception is not None:
        raise coordinator.last_exception

    body = coordinator.data

    err = None
    responseData = None
    # MFA Code is wrong, so display message.
    # {"code": "Mfa.Wrong.Code","message": "Mfa wrong code", "additionalData": [{"code": "Mfa.Available.Attempts","message": "4"}]}
    if "code" in body:
        if body["code"] == CODE_MFA_CODE_WRONG:
            err = (
                body["message"]
                + " "
                + body["additionalData"][0]["message"]
                + " retries remaining"
            )
    # Successful Login
    # {"customerId": "<CUSTOMER_ID>","token": "<ACCESS_TOKEN>"}
    if CUSTOMER_ID in body:
        responseData = {CUSTOMER_ID: body[CUSTOMER_ID], TOKEN: body[TOKEN]}

    return {"title": str(data[CONF_EMAIL]), "data": responseData, "error": err}


class ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Ryanair."""

    VERSION = 2

    def __init__(self) -> None:
        """Init."""
        self._fingerprint: str | None = None

    async def async_step_mfa(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the MFA step."""

        errors = {}
        placeholder = ""

        try:
            info = await validate_mfa_input(self.hass, user_input)
        except CannotConnect:
            errors["base"] = "cannot_connect"
        else:
            if info["error"] is not None:
                errors["base"] = "invalid_auth"
                placeholder = info["error"]
            elif CUSTOMER_ID in info["data"]:
                data = dict(user_input)
                fingerprint = user_input[CONF_DEVICE_FINGERPRINT]

                if CUSTOMERS not in data:
                    data[CUSTOMERS] = {}

                data[CUSTOMERS][self._fingerprint] = {
                    CONF_DEVICE_FINGERPRINT: fingerprint,
                    CUSTOMER_ID: info["data"][CUSTOMER_ID],
                    TOKEN: info["data"][TOKEN],
                    MFA_TOKEN: user_input[MFA_TOKEN],
                    CONF_EMAIL: user_input[CONF_EMAIL],
                }

                existing_entries = self.hass.config_entries.async_entries(DOMAIN)

                # Check if an entry already exists with the same username
                existing_entry = next(
                    (
                        entry
                        for entry in existing_entries
                        if entry.data.get(CONF_EMAIL) == user_input[CONF_EMAIL]
                    ),
                    None,
                )

                if existing_entry is not None:
                    # Update specific data in the entry
                    updated_data = existing_entry.data.copy()
                    # Merge the import_data into the entry_data
                    updated_data.update(data)
                    # Update the entry with the new data
                    self.hass.config_entries.async_update_entry(
                        existing_entry, data=updated_data
                    )
                return self.async_create_entry(title=info["title"], data=data)

        return self.async_show_form(
            step_id="mfa",
            data_schema=STEP_MFA,
            description_placeholders={"email": placeholder},
            errors=errors,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_DATA_SCHEMA,
                description_placeholders={"retries": ""},
            )

        errors = {}
        placeholder = ""

        self._fingerprint = generate_device_fingerprint(user_input[CONF_EMAIL])

        data = dict(user_input)

        if CUSTOMERS not in data:
            data[CUSTOMERS] = {}

        data[CUSTOMERS][self._fingerprint] = {
            CONF_DEVICE_FINGERPRINT: self._fingerprint,
            CONF_EMAIL: user_input[CONF_EMAIL],
            CONF_PASSWORD: user_input[CONF_PASSWORD],
        }

        existing_entries = self.hass.config_entries.async_entries(DOMAIN)

        # Check if an entry already exists with the same username
        existing_entry = next(
            (
                entry
                for entry in existing_entries
                if entry.data.get(CONF_EMAIL) == user_input[CONF_EMAIL]
            ),
            None,
        )

        if existing_entry is not None:
            # Update specific data in the entry
            updated_data = existing_entry.data.copy()
            # Merge the import_data into the entry_data
            updated_data.update(data)
            # Update the entry with the new data
            self.hass.config_entries.async_update_entry(
                existing_entry, data=updated_data
            )
        try:
            info = await validate_input(self.hass, data, self._fingerprint)
        except CannotConnect:
            errors["base"] = "cannot_connect"
        else:
            if info["error"] is not None:
                errors["base"] = "invalid_auth"
                placeholder = info["error"]
            elif info["data"] is not None:
                # MFA TOKEN initiates MFA code capture
                if MFA_TOKEN in info["data"]:
                    return self.async_show_form(
                        step_id="mfa",
                        data_schema=STEP_MFA,
                        description_placeholders={
                            "email": "Please enter the 8 character verification code sent to "
                            + info["title"]
                        },
                    )
                if CUSTOMER_ID in info["data"]:
                    if CUSTOMERS not in data:
                        data[CUSTOMERS] = {}

                    data[CUSTOMERS][self._fingerprint] = {
                        CONF_DEVICE_FINGERPRINT: self._fingerprint,
                        CUSTOMER_ID: info["data"][CUSTOMER_ID],
                        TOKEN: info["data"][TOKEN],
                    }

                    existing_entries = self.hass.config_entries.async_entries(DOMAIN)

                    # Check if an entry already exists with the same username
                    existing_entry = next(
                        (
                            entry
                            for entry in existing_entries
                            if entry.data.get(CONF_EMAIL) == user_input[CONF_EMAIL]
                        ),
                        None,
                    )

                    if existing_entry is not None:
                        # Update specific data in the entry
                        updated_data = existing_entry.data.copy()
                        # Merge the import_data into the entry_data
                        updated_data.update(data)
                        # Update the entry with the new data
                        self.hass.config_entries.async_update_entry(
                            existing_entry, data=updated_data
                        )
                    return self.async_create_entry(title=info["title"], data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            description_placeholders={"retries": placeholder},
            errors=errors,
        )
