"""Ryanair Coordinator."""
from datetime import timedelta
import logging
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONTENT_TYPE_JSON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from .const import (
    DOMAIN,
    HOST,
    USER_PROFILE,
    ORDERS,
    V,
    CUSTOMERS,
    ACCOUNTS,
    ACCOUNT_LOGIN,
    CONF_DEVICE_FINGERPRINT,
    CONF_POLICY_AGREED,
    MFA_CODE,
    ACCOUNT_VERIFICATION,
    DEVICE_VERIFICATION,
    MFA_TOKEN,
    CONF_AUTH_TOKEN,
    PROFILE,
    CUSTOMER_ID,
    TOKEN,
    REMEMBER_ME_TOKEN,
    DETAILS,
)
from .errors import RyanairError, InvalidAuth, APIRatelimitExceeded, UnknownError
from homeassistant.exceptions import ConfigEntryAuthFailed

_LOGGER = logging.getLogger(__name__)

USER_PROFILE_URL = HOST + USER_PROFILE + V
ORDERS_URL = HOST + ORDERS + V


async def refreshToken(self):
    resp = await self.session.request(
        method="GET",
        url=USER_PROFILE_URL
        + ACCOUNTS
        + "/"
        + self.customerId
        + "/"
        + REMEMBER_ME_TOKEN,
        headers={
            CONF_DEVICE_FINGERPRINT: self.fingerprint,
            CONF_AUTH_TOKEN: self.token,
        },
    )
    body = await resp.json()

    return body


async def getUserProfile(self):
    resp = await self.session.request(
        method="GET",
        url=ORDERS_URL + ORDERS + self.customerId + "/" + DETAILS,
        headers={
            "Content-Type": CONTENT_TYPE_JSON,
            CONF_DEVICE_FINGERPRINT: self.fingerprint,
            CONF_AUTH_TOKEN: self.token,
        },
    )
    body = await resp.json()

    return body


async def getFlights(self):
    resp = await self.session.request(
        method="GET",
        url=USER_PROFILE_URL + CUSTOMERS + "/" + self.customerId + "/" + PROFILE,
        headers={
            "Content-Type": CONTENT_TYPE_JSON,
            CONF_DEVICE_FINGERPRINT: self.fingerprint,
            CONF_AUTH_TOKEN: self.token,
        },
    )
    body = await resp.json()

    return body


class RyanairFlightsCoordinator(DataUpdateCoordinator):
    """Flights Coordinator"""

    def __init__(self, hass: HomeAssistant, session, data) -> None:
        """Initialize coordinator."""

        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="Ryanair",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=300),
        )

        self.session = session
        self.customerId = data[CUSTOMER_ID]
        self.fingerprint = data[CONF_DEVICE_FINGERPRINT]
        self.token = data[TOKEN]

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        try:
            body = await getUserProfile(self)

            if ("access-denied" in body and body["cause"] == "NOT AUTHENTICATED") or (
                "type" in body and body["type"] == "CLIENT_ERROR"
            ):
                refreshedToken = await refreshToken(self)

                self.customerId = refreshedToken[CUSTOMER_ID]
                self.token = refreshedToken[TOKEN]

                body = await getUserProfile(self)

        except InvalidAuth as err:
            raise ConfigEntryAuthFailed from err
        except RyanairError as err:
            raise UpdateFailed(str(err)) from err
        except ValueError as err:
            err_str = str(err)

            if "Invalid authentication credentials" in err_str:
                raise InvalidAuth from err
            if "API rate limit exceeded." in err_str:
                raise APIRatelimitExceeded from err

            _LOGGER.exception("Unexpected exception")
            raise UnknownError from err

        return body


class RyanairProfileCoordinator(DataUpdateCoordinator):
    """User Profile Coordinator"""

    def __init__(self, hass: HomeAssistant, session, data) -> None:
        """Initialize coordinator."""

        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="Ryanair",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=300),
        )

        self.session = session
        self.customerId = data[CUSTOMER_ID]
        self.fingerprint = data[CONF_DEVICE_FINGERPRINT]
        self.token = data[TOKEN]

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        try:
            body = await getFlights(self)

            if ("access-denied" in body and body["cause"] == "NOT AUTHENTICATED") or (
                "type" in body and body["type"] == "CLIENT_ERROR"
            ):
                refreshedToken = await refreshToken(self)

                self.customerId = refreshedToken[CUSTOMER_ID]
                self.token = refreshedToken[TOKEN]

                body = await getFlights(self)

        except InvalidAuth as err:
            raise ConfigEntryAuthFailed from err
        except RyanairError as err:
            raise UpdateFailed(str(err)) from err
        except ValueError as err:
            err_str = str(err)

            if "Invalid authentication credentials" in err_str:
                raise InvalidAuth from err
            if "API rate limit exceeded." in err_str:
                raise APIRatelimitExceeded from err

            _LOGGER.exception("Unexpected exception")
            raise UnknownError from err

        return body


class RyanairMfaCoordinator(DataUpdateCoordinator):
    """MFA coordinator."""

    def __init__(self, hass: HomeAssistant, session, data) -> None:
        """Initialize coordinator."""

        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="Ryanair",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=300),
        )

        self.session = session
        self.mfaCode = data[MFA_CODE]
        self.mfaToken = data[MFA_TOKEN]
        self.fingerprint = data[CONF_DEVICE_FINGERPRINT]

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        try:
            resp = await self.session.request(
                method="PUT",
                url=USER_PROFILE_URL + ACCOUNT_VERIFICATION + "/" + DEVICE_VERIFICATION,
                headers={
                    "Content-Type": CONTENT_TYPE_JSON,
                    CONF_DEVICE_FINGERPRINT: self.fingerprint,
                },
                json={MFA_CODE: self.mfaCode, MFA_TOKEN: self.mfaToken},
            )
            body = await resp.json()
            # session expired
            # {'access-denied': True, 'message': 'Full authentication is required to access this resource.', 'cause': 'NOT AUTHENTICATED'}

        except InvalidAuth as err:
            raise ConfigEntryAuthFailed from err
        except RyanairError as err:
            raise UpdateFailed(str(err)) from err
        except ValueError as err:
            err_str = str(err)

            if "Invalid authentication credentials" in err_str:
                raise InvalidAuth from err
            if "API rate limit exceeded." in err_str:
                raise APIRatelimitExceeded from err

            _LOGGER.exception("Unexpected exception")
            raise UnknownError from err

        return body


class RyanairCoordinator(DataUpdateCoordinator):
    """Data coordinator."""

    def __init__(self, hass: HomeAssistant, session, data) -> None:
        """Initialize coordinator."""

        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="Ryanair",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=300),
        )

        self.session = session
        self.email = data[CONF_EMAIL]
        self.password = data[CONF_PASSWORD]
        self.fingerprint = data[CONF_DEVICE_FINGERPRINT]

    async def _async_update_data(self):
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        try:
            resp = await self.session.request(
                method="POST",
                url=USER_PROFILE_URL + ACCOUNT_LOGIN,
                headers={
                    "Content-Type": CONTENT_TYPE_JSON,
                    CONF_DEVICE_FINGERPRINT: self.fingerprint,
                },
                json={
                    CONF_EMAIL: self.email,
                    CONF_PASSWORD: self.password,
                    CONF_POLICY_AGREED: "true",
                },
            )
            body = await resp.json()

        except InvalidAuth as err:
            raise ConfigEntryAuthFailed from err
        except RyanairError as err:
            raise UpdateFailed(str(err)) from err
        except ValueError as err:
            err_str = str(err)

            if "Invalid authentication credentials" in err_str:
                raise InvalidAuth from err
            if "API rate limit exceeded." in err_str:
                raise APIRatelimitExceeded from err

            _LOGGER.exception("Unexpected exception")
            raise UnknownError from err

        return body
