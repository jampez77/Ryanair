"""Ryanair Boarding Pass"""
from __future__ import annotations
from homeassistant.helpers.entity import DeviceInfo
from .coordinator import RyanairProfileCoordinator, RyanairFlightsCoordinator, RyanairBoardingPassCoordinator
from homeassistant.util import dt as dt_util
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util.json import JsonObjectType
import logging
from pathlib import Path
from .const import (
    DOMAIN,
    CUSTOMER_ID,
    ACCESS_DENIED,
    CAUSE,
    NOT_AUTHENTICATED,
    OPEN_TIME,
    CLOSE_TIME,
    TYPE,
    EMAIL,
    RECORD_LOCATOR
)
from aiohttp import ClientError
from typing import Any
import re
from homeassistant.components.image import (
    ImageEntity,
    ImageEntityDescription,
)
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)
_LOGGER = logging.getLogger(__name__)


def deviceInfo(bookingRef) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, f"Ryanair_{bookingRef}")},
        manufacturer="Ryanair",
        name=bookingRef,
        configuration_url="https://github.com/jampez77/Ryanair/",
    )


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the sensor platform."""
    session = async_get_clientsession(hass)
    profileCoordinator = RyanairProfileCoordinator(hass, session, config)

    name = config[CUSTOMER_ID]

    flightsCoordinator = RyanairFlightsCoordinator(hass, session, config)

    name = config[CUSTOMER_ID]

    sensors = []

    if "items" in flightsCoordinator.data and len(flightsCoordinator.data["items"]) > 0:
        for item in flightsCoordinator.data["items"]:

            flights = item["rawBooking"]["flights"]
            bookingRef = item["rawBooking"]["recordLocator"]
            seats = item["rawBooking"]["seats"]
            passengers = item["rawBooking"]["passengers"]

            for flight in flights:
                for seat in seats:
                    if seat["journeyNum"] == flight["journeyNum"]:
                        checkedInPassengers = []
                        for passenger in passengers:
                            if "checkins" in item["rawBooking"] and len(item["rawBooking"]["checkins"]) > 0:
                                for checkin in item["rawBooking"]["checkins"]:
                                    if checkin["journeyNum"] == flight["journeyNum"] and checkin["paxNum"] == passenger["paxNum"] and checkin["status"] == "checkin":
                                        checkedInPassengers.append(checkin)

                        if len(checkedInPassengers) == len(passengers):

                            boardpassData = {
                                EMAIL: profileCoordinator.data["email"],
                                RECORD_LOCATOR: bookingRef
                            }
                            boardPassCoordinator = RyanairBoardingPassCoordinator(
                                hass, session, boardpassData)

                            await boardPassCoordinator.async_refresh()

                            boardingPassDescription = ImageEntityDescription(
                                key=f"Ryanair_boarding_pass{name}",
                                name=name,
                            )

                            for boardingPass in boardPassCoordinator.data:
                                sensors.append(RyanairBoardingPassImage(hass,
                                                                        boardingPass, bookingRef, name, boardingPassDescription))

    async_add_entities(sensors, update_before_add=True)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Setup sensors from a config entry created in the integrations UI."""
    config = hass.data[DOMAIN][entry.entry_id]
    # Update our config to include new repos and remove those that have been removed.
    if entry.options:
        config.update(entry.options)

    session = async_get_clientsession(hass)

    profileCoordinator = RyanairProfileCoordinator(hass, session, entry.data)

    await profileCoordinator.async_refresh()

    flightsCoordinator = RyanairFlightsCoordinator(hass, session, config)

    await flightsCoordinator.async_refresh()

    sensors = []

    if "items" in flightsCoordinator.data and len(flightsCoordinator.data["items"]) > 0:
        for item in flightsCoordinator.data["items"]:

            flights = item["rawBooking"]["flights"]
            bookingRef = item["rawBooking"]["recordLocator"]
            seats = item["rawBooking"]["seats"]
            passengers = item["rawBooking"]["passengers"]

            for flight in flights:
                for seat in seats:
                    if seat["journeyNum"] == flight["journeyNum"]:
                        checkedInPassengers = []
                        for passenger in passengers:
                            if "checkins" in item["rawBooking"] and len(item["rawBooking"]["checkins"]) > 0:
                                for checkin in item["rawBooking"]["checkins"]:
                                    if checkin["journeyNum"] == flight["journeyNum"] and checkin["paxNum"] == passenger["paxNum"] and checkin["status"] == "checkin":
                                        checkedInPassengers.append(passenger)

            if len(checkedInPassengers) == len(passengers):

                boardpassData = {
                    EMAIL: profileCoordinator.data["email"],
                    RECORD_LOCATOR: bookingRef
                }
                boardPassCoordinator = RyanairBoardingPassCoordinator(
                    hass, session, boardpassData)

                await boardPassCoordinator.async_refresh()

                for boardingPass in boardPassCoordinator.data:
                    flightName = "(" + boardingPass["flight"]["label"] + ") " + \
                        boardingPass["departure"]["name"] + \
                        " - " + boardingPass["arrival"]["name"]

                    seat = boardingPass["seat"]["designator"]

                    passenger = boardingPass["name"]["first"] + \
                        " " + boardingPass["name"]["last"]

                    name = passenger + ": " + \
                        flightName + "(" + seat + ")"

                    boardingPassDescription = ImageEntityDescription(
                        key=f"Ryanair_boarding_pass{name}",
                        name=name,
                    )

                    if boardingPass["paxType"] != "INF":
                        sensors.append(RyanairBoardingPassImage(hass,
                                                                boardingPass, bookingRef, name, boardingPassDescription))

    async_add_entities(sensors, update_before_add=True)


class RyanairBoardingPassImage(ImageEntity):
    """Representation of an image entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        boardingPassData: JsonObjectType,
        bookingRef: str,
        name: str,
        description: ImageEntityDescription,
    ) -> None:
        """Initialize."""
        super().__init__(hass)
        self.bookingRef = bookingRef
        self._attr_device_info = deviceInfo(self.bookingRef)
        self._attr_unique_id = f"Ryanair_boarding_pass-{self.bookingRef}-{name}-{description.key}".lower(
        )
        self.boardingPassData = boardingPassData
        self._attrs: dict[str, Any] = {}
        self.entity_description = description
        self._state = None
        self._name = name
        self._available = True
        fileName = re.sub(
            "[\W_]", "", self.boardingPassData['barcode']) + ".png"

        self.file_name = fileName

    async def async_added_to_hass(self):
        """Set the update time."""
        self._attr_image_last_updated = dt_util.utcnow()

    async def async_image(self) -> bytes | None:
        """Return bytes of image."""
        image_path = Path(__file__).parent / self.file_name
        return await self.hass.async_add_executor_job(image_path.read_bytes)

    @property
    def icon(self) -> str:
        """Return a representative icon."""
        return "mdi:qrcode"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:

        attrs = {
            "name": self.boardingPassData["name"]
        }
        self._attrs = attrs
        return self._attrs

    async def async_update(self) -> None:
        """Update the entity.

        Only used by the generic entity update service.
        """
        try:
            self._state = str("BP")
            self._available = True
        except ClientError:
            self._available = False
            _LOGGER.exception(
                "Error retrieving data from Ryanair for sensor %s", self.name
            )
