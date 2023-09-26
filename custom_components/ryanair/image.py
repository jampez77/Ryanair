"""Ryanair Boarding Pass"""
from __future__ import annotations
from datetime import datetime
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
from io import BytesIO
from pathlib import Path
from .const import (
    DOMAIN,
    BOOKING_REFERENCES,
    BOARDING_PASS_HEADERS,
    EMAIL,
    RECORD_LOCATOR,
    LOCAL_FOLDER,
    BOARDING_PASSES_URI
)
from aiohttp import ClientError
from typing import Any
import re
from homeassistant.components.image import (
    ImageEntity,
    ImageEntityDescription,
)
from homeassistant.util.json import load_json_object
BOARDING_PASS_PERSISTENCE = LOCAL_FOLDER + BOARDING_PASS_HEADERS


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

    sensors = []

    data = load_json_object(BOARDING_PASS_PERSISTENCE)

    if BOOKING_REFERENCES in data and EMAIL in data:
        for bookingRef in data[BOOKING_REFERENCES]:
            boardpassData = {
                EMAIL: data[EMAIL],
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

                sensors.append(RyanairBoardingPassImage(
                    hass, boardingPass, bookingRef, name, boardingPassDescription))

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

    sensors = []

    data = load_json_object(BOARDING_PASS_PERSISTENCE)

    if BOOKING_REFERENCES in data and EMAIL in data:
        for bookingRef in data[BOOKING_REFERENCES]:
            boardpassData = {
                EMAIL: data[EMAIL],
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

                sensors.append(RyanairBoardingPassImage(
                    hass, boardingPass, bookingRef, name, boardingPassDescription))

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
        self.boardingPassData = boardingPassData
        flightNumber = self.boardingPassData["flight"]["carrierCode"] + \
            self.boardingPassData["flight"]["number"]
        self._attr_device_info = deviceInfo(
            self.bookingRef + " " + flightNumber)
        self._attr_unique_id = f"Ryanair_boarding_pass-{flightNumber}-{self.bookingRef}-{name}-{description.key}".lower(
        )

        self._attrs: dict[str, Any] = {}
        self.entity_description = description
        self._state = None
        self._name = name
        self._available = True
        self._current_qr_bytes: bytes | None = None

        print(self.name)
        if self.boardingPassData["paxType"] != "INF":
            fileName = BOARDING_PASSES_URI + re.sub(
                "[\W_]", "", self.name + self.boardingPassData["departure"]["dateUTC"]) + ".png"
        else:
            fileName = "infant_qr.png"

        self.file_name = fileName

    async def _fetch_image(self) -> bytes:
        """Fetch the Image"""
        image_path = Path(__file__).parent / self.file_name

        qr_bytes = await self.hass.async_add_executor_job(image_path.read_bytes)

        return qr_bytes

    async def async_added_to_hass(self):
        """Set the update time."""
        self._current_qr_bytes = await self._fetch_image()
        self._attr_image_last_updated = dt_util.utcnow()

    async def async_image(self) -> bytes | None:
        """Return bytes of image."""
        image_path = Path(__file__).parent / self.file_name
        return await self.hass.async_add_executor_job(image_path.read_bytes)

    @property
    def icon(self) -> str:
        """Return a representative icon."""
        return "mdi:qrcode"

    async def async_update(self) -> None:
        """Update the image entity data."""
        qr_bytes = await self._fetch_image()

        if self._current_qr_bytes is not None and qr_bytes is not None:
            dt_now = dt_util.utcnow()
            print("Aztec code has changed, reset image last updated property")
            self._attr_image_last_updated = dt_now
            self._current_qr_bytes = qr_bytes
            self.async_write_ha_state()
