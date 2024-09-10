"""Ryanair Coordinator."""
from datetime import timedelta
import logging
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONTENT_TYPE_JSON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from aiohttp import ClientSession, ClientError
import re
from aztec_code_generator import AztecCode
from .const import (
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
    REMEMBER_ME,
    X_REMEMBER_ME_TOKEN,
    ACCESS_DENIED,
    CAUSE,
    NOT_AUTHENTICATED,
    CLIENT_ERROR,
    TYPE,
    BOARDING_PASS_URL,
    BOARDING_PASSES_URI,
    BOOKING_REFERENCE,
    EMAIL,
    RECORD_LOCATOR,
    BOOKING_DETAILS_URL,
    AUTH_TOKEN,
    BOOKING_INFO,
    DOMAIN,
    CLIENT_VERSION,
)
from .errors import RyanairError, InvalidAuth, APIRatelimitExceeded, UnknownError
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.util.json import load_json_object, JsonObjectType
from pathlib import Path
_LOGGER = logging.getLogger(__name__)

USER_PROFILE_URL = HOST + USER_PROFILE + V
ORDERS_URL = HOST + ORDERS + V


async def async_load_json_object(hass: HomeAssistant, path: Path) -> JsonObjectType:
    return await hass.async_add_executor_job(load_json_object, path)


async def rememberMeToken(self, userData):

    async with ClientSession() as session:
        rememberMeTokenResp = await session.request(
            method="GET",
            url=USER_PROFILE_URL
            + ACCOUNTS
            + "/"
            + userData[CUSTOMER_ID]
            + "/"
            + REMEMBER_ME_TOKEN,
            headers={
                CONF_DEVICE_FINGERPRINT: userData[CONF_DEVICE_FINGERPRINT],
                CONF_AUTH_TOKEN: userData[TOKEN],
            },
        )
        rememberMeTokenResponse = await rememberMeTokenResp.json()

        if rememberMeTokenResponse is not None and ((ACCESS_DENIED in rememberMeTokenResponse and rememberMeTokenResponse[CAUSE] == NOT_AUTHENTICATED) or (
            TYPE in rememberMeTokenResponse and rememberMeTokenResponse[TYPE] == CLIENT_ERROR
        )):
            authResponse = await authenticateUser(self, userData)

            userData[TOKEN] = authResponse[TOKEN]
            userData[CUSTOMER_ID] = authResponse[CUSTOMER_ID]
        else:
            userData[X_REMEMBER_ME_TOKEN] = rememberMeTokenResponse[TOKEN]

            entries = self.hass.config_entries.async_entries(DOMAIN)
            for entry in entries:
                updated_data = entry.data.copy()
                updated_data.update(self.data)
                self.hass.config_entries.async_update_entry(
                    entry, data=updated_data)

        del rememberMeTokenResponse

        return userData


async def refreshToken(self, userData):
    rememberMeResp = await self.session.request(
        method="GET",
        url=USER_PROFILE_URL + ACCOUNTS + "/" + REMEMBER_ME,
        headers={
            CONF_DEVICE_FINGERPRINT: userData[CONF_DEVICE_FINGERPRINT],
            X_REMEMBER_ME_TOKEN: userData[X_REMEMBER_ME_TOKEN],
        },
    )
    rememberMeResponse = await rememberMeResp.json()

    users = await rememberMeToken(self, userData)

    users[TOKEN] = rememberMeResponse[TOKEN]

    entries = self.hass.config_entries.async_entries(DOMAIN)
    for entry in entries:
        updated_data = entry.data.copy()
        updated_data.update(self.data)
        self.hass.config_entries.async_update_entry(
            entry, data=updated_data)

    return users


async def getFlights(self, data):
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
            _LOGGER.error(f"Error fetching flights: {e}")
            raise UpdateFailed(f"Error fetching flights: {e}")
        finally:
            del resp

    return body


async def getUserProfile(self, data):
    resp = await self.session.request(
        method="GET",
        url=USER_PROFILE_URL + CUSTOMERS + "/" +
        data[CUSTOMER_ID] + "/" + PROFILE,
        headers={
            "Content-Type": CONTENT_TYPE_JSON,
            CONF_DEVICE_FINGERPRINT: data[CONF_DEVICE_FINGERPRINT],
            CONF_AUTH_TOKEN: data[TOKEN],
        },
    )
    body = await resp.json()
    return body


async def getBoardingPasses(self, data, headers):
    resp = await self.session.request(
        method="POST",
        url=BOARDING_PASS_URL,
        headers={
            "Content-Type": CONTENT_TYPE_JSON,
            CONF_DEVICE_FINGERPRINT: data[CONF_DEVICE_FINGERPRINT],
            CONF_AUTH_TOKEN: data[TOKEN],
        },
        json={
            EMAIL: headers[EMAIL],
            RECORD_LOCATOR: headers[RECORD_LOCATOR]
        }
    )
    body = await resp.json()
    return body


async def getBookingDetails(self, data, bookingInfo):
    resp = await self.session.request(
        method="POST",
        url=BOOKING_DETAILS_URL,
        headers={
            CLIENT_VERSION: "9.9.9",
            "Content-Type": CONTENT_TYPE_JSON,
            CONF_DEVICE_FINGERPRINT: data[CONF_DEVICE_FINGERPRINT],
            CONF_AUTH_TOKEN: data[TOKEN],
        },
        json={
            AUTH_TOKEN: data[TOKEN],
            BOOKING_INFO: bookingInfo
        }
    )
    body = await resp.json()
    return body


async def authenticateUser(self, userData, fingerprint):
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
    body = await resp.json()
    return body


class RyanairBookingDetailsCoordinator(DataUpdateCoordinator):
    """Booking Details Coordinator"""

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
                self.data = await rememberMeToken(self, self.data)

            body = await getBookingDetails(self, self.data)

            if (ACCESS_DENIED in body and body[CAUSE] == NOT_AUTHENTICATED) or (
                TYPE in body and body[TYPE] == CLIENT_ERROR
            ):
                self.data = await refreshToken(self, self.data)

                body = await getBookingDetails(self, self.data)

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
            raise UpdateFailed(f"Error communicating with API: {error}")


class RyanairBoardingPassCoordinator(DataUpdateCoordinator):
    """Boarding Pass Coordinator"""

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
            boardingPassData = await async_load_json_object(
                self.hass, "")

            if self.fingerprint in boardingPassData:
                bookingReferences = boardingPassData[self.fingerprint]

            if len(bookingReferences) > 0:
                for bookingRef in bookingReferences:
                    headers = {
                        EMAIL: self.email,
                        RECORD_LOCATOR: bookingRef[BOOKING_REFERENCE]
                    }

                    if X_REMEMBER_ME_TOKEN not in self.data:
                        self.data = await rememberMeToken(self, self.data)

                    body = await getBoardingPasses(self, self.data, headers)

                    if body is not None and ((ACCESS_DENIED in body and body[CAUSE] == NOT_AUTHENTICATED) or (
                        TYPE in body and body[TYPE] == CLIENT_ERROR
                    )):
                        self.data = await refreshToken(self, self.data)

                        body = await getBoardingPasses(self, self.data, headers)

                    if body is not None:
                        for boardingPass in body:
                            if "barcode" in boardingPass:
                                aztec_code = AztecCode(boardingPass['barcode'])

                                flightName = "(" + boardingPass["flight"]["label"] + ") " + \
                                    boardingPass["departure"]["name"] + \
                                    " - " + boardingPass["arrival"]["name"]

                                seat = boardingPass["seat"]["designator"]

                                passenger = boardingPass["name"]["first"] + \
                                    " " + boardingPass["name"]["last"]

                                name = passenger + ": " + \
                                    flightName + "(" + seat + ")"

                                fileName = re.sub(
                                    "[\W_]", "", name + boardingPass["departure"]["dateUTC"]) + ".png"

                                aztec_code.save(
                                    Path(__file__).parent / BOARDING_PASSES_URI / fileName, module_size=16)
            else:
                body = None

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
            raise UpdateFailed(f"Error communicating with API: {error}")


class RyanairFlightsCoordinator(DataUpdateCoordinator):
    """Flights Coordinator"""

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
                self.data = await rememberMeToken(self, self.data)

            body = await getFlights(self, self.data)

            if (ACCESS_DENIED in body and body[CAUSE] == NOT_AUTHENTICATED) or (
                TYPE in body and body[TYPE] == CLIENT_ERROR
            ):
                self.data = await refreshToken(self, self.data)

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
    """User Profile Coordinator"""

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
        self.data = data[CUSTOMERS][fingerprint]
        self.fingerprint = fingerprint

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        try:

            if CONF_DEVICE_FINGERPRINT in self.data:

                if X_REMEMBER_ME_TOKEN not in self.data:
                    self.data = await rememberMeToken(self, self.data)

                body = await getUserProfile(self, self.data)

                if (ACCESS_DENIED in body and body[CAUSE] == NOT_AUTHENTICATED) or (
                    TYPE in body and body[TYPE] == CLIENT_ERROR
                ):
                    self.data = await refreshToken(self, self.data)

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
            raise UpdateFailed(f"Error communicating with API: {error}")


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
            raise UpdateFailed(f"Error communicating with API: {error}")


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
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
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
