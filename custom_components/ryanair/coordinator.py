"""Ryanair Coordinator."""

from datetime import timedelta
import logging
from pathlib import Path
import re

from aiohttp import ClientError, ClientSession
from aztec_code_generator import AztecCode

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONTENT_TYPE_JSON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util.json import JsonObjectType, load_json_object

from .const import (
    ACCESS_DENIED,
    ACCOUNT_LOGIN,
    ACCOUNT_VERIFICATION,
    ACCOUNTS,
    AUTH_TOKEN,
    BOARDING_PASS_URL,
    BOARDING_PASSES_URI,
    BOOKING_DETAILS_URL,
    BOOKING_INFO,
    BOOKING_REFERENCE,
    CAUSE,
    CLIENT_ERROR,
    CLIENT_VERSION,
    CONF_AUTH_TOKEN,
    CONF_DEVICE_FINGERPRINT,
    CONF_POLICY_AGREED,
    CUSTOMER_ID,
    CUSTOMERS,
    DETAILS,
    DEVICE_VERIFICATION,
    DOMAIN,
    EMAIL,
    HOST,
    MFA_CODE,
    MFA_TOKEN,
    NOT_AUTHENTICATED,
    ORDERS,
    PROFILE,
    RECORD_LOCATOR,
    REMEMBER_ME,
    REMEMBER_ME_TOKEN,
    TOKEN,
    TYPE,
    USER_PROFILE,
    X_REMEMBER_ME_TOKEN,
    V,
)
from .errors import APIRatelimitExceeded, InvalidAuth, RyanairError, UnknownError

_LOGGER = logging.getLogger(__name__)

USER_PROFILE_URL = HOST + USER_PROFILE + V
ORDERS_URL = HOST + ORDERS + V


async def async_load_json_object(hass: HomeAssistant, path: Path) -> JsonObjectType:
    """Load JSON object."""
    return await hass.async_add_executor_job(load_json_object, path)


async def rememberMeToken(self, userData, fingerprint):
    """Remember me token."""
    async with ClientSession() as session:
        if CUSTOMERS in userData and fingerprint in userData[CUSTOMERS]:
            data = userData[CUSTOMERS][fingerprint]
        else:
            data = userData

        rememberMeTokenResp = await session.request(
            method="GET",
            url=USER_PROFILE_URL
            + ACCOUNTS
            + "/"
            + data[CUSTOMER_ID]
            + "/"
            + REMEMBER_ME_TOKEN,
            headers={
                CONF_DEVICE_FINGERPRINT: data[CONF_DEVICE_FINGERPRINT],
                CONF_AUTH_TOKEN: data[TOKEN],
            },
        )
        rememberMeTokenResponse = await rememberMeTokenResp.json()

        if rememberMeTokenResponse is not None and (
            (
                ACCESS_DENIED in rememberMeTokenResponse
                and rememberMeTokenResponse[CAUSE] == NOT_AUTHENTICATED
            )
            or (
                TYPE in rememberMeTokenResponse
                and rememberMeTokenResponse[TYPE] == CLIENT_ERROR
            )
        ):
            authResponse = await authenticateUser(self, userData, fingerprint)

            userData[CUSTOMERS][fingerprint][TOKEN] = authResponse[TOKEN]
            userData[CUSTOMERS][fingerprint][CUSTOMER_ID] = authResponse[CUSTOMER_ID]
        else:
            if CUSTOMERS in userData and fingerprint in userData[CUSTOMERS]:
                userData[CUSTOMERS][fingerprint][X_REMEMBER_ME_TOKEN] = (
                    rememberMeTokenResponse[TOKEN]
                )
            else:
                data[X_REMEMBER_ME_TOKEN] = rememberMeTokenResponse[TOKEN]

            entries = self.hass.config_entries.async_entries(DOMAIN)
            for entry in entries:
                updated_data = entry.data.copy()
                updated_data.update(userData)
                self.hass.config_entries.async_update_entry(entry, data=updated_data)

        del rememberMeTokenResponse

        return userData


async def refreshToken(self, userData, fingerprint):
    """Refresh Token."""

    data = userData[CUSTOMERS][fingerprint]
    rememberMeResp = await self.session.request(
        method="GET",
        url=USER_PROFILE_URL + ACCOUNTS + "/" + REMEMBER_ME,
        headers={
            CONF_DEVICE_FINGERPRINT: data[CONF_DEVICE_FINGERPRINT],
            X_REMEMBER_ME_TOKEN: data[X_REMEMBER_ME_TOKEN],
        },
    )
    rememberMeResponse = await rememberMeResp.json()

    users = await rememberMeToken(self, userData, fingerprint)

    users[TOKEN] = rememberMeResponse[TOKEN]

    entries = self.hass.config_entries.async_entries(DOMAIN)
    for entry in entries:
        updated_data = entry.data.copy()
        updated_data.update(users)
        self.hass.config_entries.async_update_entry(entry, data=updated_data)
        users = updated_data

    return users


async def getFlights(self, data):
    """Get Flights."""
    body = None
    async with ClientSession() as session:
        try:
            resp = await session.request(
                method="GET",
                url=ORDERS_URL + ORDERS + data[CUSTOMER_ID] + "/" + DETAILS,
                headers={
                    "Content-Type": CONTENT_TYPE_JSON,
                    CONF_DEVICE_FINGERPRINT: data[CONF_DEVICE_FINGERPRINT],
                    CONF_AUTH_TOKEN: data[TOKEN],
                },
            )
            body = await resp.json()
            # Process body if needed
        except ClientError as e:
            raise UpdateFailed(f"Error fetching flights: {e}") from e
        finally:
            del resp

    return body


async def getUserProfile(self, data):
    """Get user profile."""
    resp = await self.session.request(
        method="GET",
        url=USER_PROFILE_URL + CUSTOMERS + "/" + data[CUSTOMER_ID] + "/" + PROFILE,
        headers={
            "Content-Type": CONTENT_TYPE_JSON,
            CONF_DEVICE_FINGERPRINT: data[CONF_DEVICE_FINGERPRINT],
            CONF_AUTH_TOKEN: data[TOKEN],
        },
    )

    return await resp.json()


async def getBoardingPasses(self, data, headers):
    """Get boarding passes."""
    resp = await self.session.request(
        method="POST",
        url=BOARDING_PASS_URL,
        headers={
            "Content-Type": CONTENT_TYPE_JSON,
            CONF_DEVICE_FINGERPRINT: data[CONF_DEVICE_FINGERPRINT],
            CONF_AUTH_TOKEN: data[TOKEN],
        },
        json={EMAIL: headers[EMAIL], RECORD_LOCATOR: headers[RECORD_LOCATOR]},
    )

    return await resp.json()


async def getBookingDetails(self, data, bookingInfo):
    """Get booking details."""
    resp = await self.session.request(
        method="POST",
        url=BOOKING_DETAILS_URL,
        headers={
            CLIENT_VERSION: "9.9.9",
            "Content-Type": CONTENT_TYPE_JSON,
            CONF_DEVICE_FINGERPRINT: data[CONF_DEVICE_FINGERPRINT],
            CONF_AUTH_TOKEN: data[TOKEN],
        },
        json={AUTH_TOKEN: data[TOKEN], BOOKING_INFO: bookingInfo},
    )

    return await resp.json()


async def authenticateUser(self, userData, fingerprint):
    """Authenticate USer."""
    resp = await self.session.request(
        method="POST",
        url=USER_PROFILE_URL + ACCOUNT_LOGIN,
        headers={
            "Content-Type": CONTENT_TYPE_JSON,
            CONF_DEVICE_FINGERPRINT: fingerprint,
        },
        json={
            CONF_EMAIL: userData[CONF_EMAIL],
            CONF_PASSWORD: userData[CONF_PASSWORD],
            CONF_POLICY_AGREED: "true",
        },
    )

    return await resp.json()


class RyanairBookingDetailsCoordinator(DataUpdateCoordinator):
    """Booking Details Coordinator."""

    def __init__(self, hass: HomeAssistant, session, deviceFingerprint, data) -> None:
        """Initialize coordinator."""

        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="Ryanair",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(minutes=5),
        )
        self.hass = hass
        self.session = session
        self.data = data
        self.fingerprint = deviceFingerprint

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        try:
            if X_REMEMBER_ME_TOKEN not in self.data:
                self.data = await rememberMeToken(self, self.data, self.fingerprint)

            body = await getBookingDetails(self, self.data)

            if (ACCESS_DENIED in body and body[CAUSE] == NOT_AUTHENTICATED) or (
                TYPE in body and body[TYPE] == CLIENT_ERROR
            ):
                self.data = await refreshToken(self, self.data, self.fingerprint)

                body = await getBookingDetails(self, self.data)

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
        except ClientError as error:
            raise UpdateFailed(f"Error communicating with API: {error}") from error
        else:
            return body


class RyanairBoardingPassCoordinator(DataUpdateCoordinator):
    """Boarding Pass Coordinator."""

    def __init__(self, hass: HomeAssistant, session, data) -> None:
        """Initialize coordinator."""

        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="Ryanair",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(5),
        )
        self.session = session
        self.email = data[EMAIL]
        self.fingerprint = data[CONF_DEVICE_FINGERPRINT]
        self.data = data

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        try:
            boardingPassData = await async_load_json_object(self.hass, "")

            if self.fingerprint in boardingPassData:
                bookingReferences = boardingPassData[self.fingerprint]

            if len(bookingReferences) > 0:
                for bookingRef in bookingReferences:
                    headers = {
                        EMAIL: self.email,
                        RECORD_LOCATOR: bookingRef[BOOKING_REFERENCE],
                    }

                    if X_REMEMBER_ME_TOKEN not in self.data:
                        self.data = await rememberMeToken(
                            self, self.data, self.fingerprint
                        )

                    body = await getBoardingPasses(self, self.data, headers)

                    if body is not None and (
                        (ACCESS_DENIED in body and body[CAUSE] == NOT_AUTHENTICATED)
                        or (TYPE in body and body[TYPE] == CLIENT_ERROR)
                    ):
                        self.data = await refreshToken(
                            self, self.data, self.fingerprint
                        )

                        body = await getBoardingPasses(self, self.data, headers)

                    if body is not None:
                        for boardingPass in body:
                            if "barcode" in boardingPass:
                                aztec_code = AztecCode(boardingPass["barcode"])

                                flightName = (
                                    "("
                                    + boardingPass["flight"]["label"]
                                    + ") "
                                    + boardingPass["departure"]["name"]
                                    + " - "
                                    + boardingPass["arrival"]["name"]
                                )

                                seat = boardingPass["seat"]["designator"]

                                passenger = (
                                    boardingPass["name"]["first"]
                                    + " "
                                    + boardingPass["name"]["last"]
                                )

                                name = passenger + ": " + flightName + "(" + seat + ")"

                                fileName = (
                                    re.sub(
                                        r"[\W_]",
                                        "",
                                        name + boardingPass["departure"]["dateUTC"],
                                    )
                                    + ".png"
                                )

                                aztec_code.save(
                                    Path(__file__).parent
                                    / BOARDING_PASSES_URI
                                    / fileName,
                                    module_size=16,
                                )
            else:
                body = None
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
        except ClientError as error:
            raise UpdateFailed(f"Error communicating with API: {error}") from error
        else:
            return body


class RyanairFlightsCoordinator(DataUpdateCoordinator):
    """Flights Coordinator."""

    def __init__(self, hass: HomeAssistant, session, data, fingerprint) -> None:
        """Initialize coordinator."""

        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="Ryanair",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(minutes=5),
        )
        self.hass = hass
        self.session = session
        self.data = data[CUSTOMERS][fingerprint]
        self.fingerprint = fingerprint

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        try:
            if X_REMEMBER_ME_TOKEN not in self.data:
                self.data = await rememberMeToken(self, self.data, self.fingerprint)

            body = await getFlights(self, self.data)

            if (ACCESS_DENIED in body and body[CAUSE] == NOT_AUTHENTICATED) or (
                TYPE in body and body[TYPE] == CLIENT_ERROR
            ):
                self.data = await refreshToken(self, self.data, self.fingerprint)

                body = await getFlights(self, self.data)

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
    """User Profile Coordinator."""

    def __init__(self, hass: HomeAssistant, session, data, fingerprint) -> None:
        """Initialize coordinator."""

        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="Ryanair",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(minutes=5),
        )
        self.session = session
        self.data = data
        self.fingerprint = fingerprint

    async def _async_update_data(self):
        """Fetch data from API endpoint."""

        try:
            if self.data is not None and CONF_DEVICE_FINGERPRINT in self.data:
                if X_REMEMBER_ME_TOKEN not in self.data:
                    self.data = await rememberMeToken(self, self.data, self.fingerprint)

                body = await getUserProfile(self, self.data)

                if (ACCESS_DENIED in body and body[CAUSE] == NOT_AUTHENTICATED) or (
                    TYPE in body and body[TYPE] == CLIENT_ERROR
                ):
                    self.data = await refreshToken(self, self.data, self.fingerprint)

                    body = await getUserProfile(self, self.data)

                return body

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
        except ClientError as error:
            raise UpdateFailed(f"Error communicating with API: {error}") from error


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
            update_interval=timedelta(5),
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
            return await resp.json()
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
        except ClientError as error:
            raise UpdateFailed(f"Error communicating with API: {error}") from error


class RyanairCoordinator(DataUpdateCoordinator):
    """Data coordinator."""

    def __init__(self, hass: HomeAssistant, session, userData, fingerprint) -> None:
        """Initialize coordinator."""

        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="Ryanair",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(5),
        )
        self.fingerprint = fingerprint
        self.session = session
        self.userData = userData

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        try:
            body = await authenticateUser(self, self.userData, self.fingerprint)
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
