"""Ryanair Boarding Pass."""

from __future__ import annotations

import datetime as dt
from datetime import datetime, timedelta
import hashlib
import os
from pathlib import Path
import re
from typing import Any
import uuid

from homeassistant.components.image import ImageEntity, ImageEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util
from homeassistant.util.json import JsonObjectType

from .const import (
    BOARDING_PASSES_URI,
    BOOKING_ID,
    CONF_DEVICE_FINGERPRINT,
    CUSTOMER_ID,
    CUSTOMERS,
    DOMAIN,
    EMAIL,
    SURROGATE_ID,
)
from .coordinator import (
    RyanairBoardingPassCoordinator,
    RyanairBookingDetailsCoordinator,
)

SCAN_INTERVAL = timedelta(5)


def deviceInfo(bookingRef) -> DeviceInfo:
    """Device info."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"Ryanair_{bookingRef}")},
        manufacturer="Ryanair",
        name=bookingRef,
        configuration_url="https://github.com/jampez77/Ryanair/",
    )


def generate_device_fingerprint(email: str) -> str:
    """Generate device fingerprint."""
    unique_id = hashlib.md5(email.encode("UTF-8")).hexdigest()
    return str(uuid.UUID(hex=unique_id))


def getFileName(name) -> str:
    """Get filename."""
    return re.sub(r"[\W_]", "", name) + ".png"


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    _: DiscoveryInfoType | None = None,
) -> None:
    """Set up the sensor platform."""
    session = async_get_clientsession(hass)

    sensors = []

    deviceFingerprint = generate_device_fingerprint(config[CONF_EMAIL])
    customerId = config[CUSTOMERS][deviceFingerprint][CUSTOMER_ID]

    bookingData = {}
    if deviceFingerprint in bookingData:
        for booking in bookingData[deviceFingerprint]:
            bookingInfo = {BOOKING_ID: booking[BOOKING_ID], SURROGATE_ID: customerId}

            bookingDetailsCoordinator = RyanairBookingDetailsCoordinator(
                hass, session, deviceFingerprint, bookingInfo
            )

            await bookingDetailsCoordinator.async_config_entry_first_refresh()

            if (
                "contacts" in bookingDetailsCoordinator.data
                and len(bookingDetailsCoordinator.data["contacts"]) > 0
            ):
                email = bookingDetailsCoordinator.data["contacts"][0]["email"]

                data = {CONF_DEVICE_FINGERPRINT: deviceFingerprint, EMAIL: email}
                boardPassCoordinator = RyanairBoardingPassCoordinator(
                    hass, session, data
                )

                await boardPassCoordinator.async_config_entry_first_refresh()

                if boardPassCoordinator.data is not None:
                    for boardingPass in boardPassCoordinator.data:
                        if "flight" in boardingPass:
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

                            boardingPassDescription = ImageEntityDescription(
                                key=f"Ryanair_boarding_pass{name}",
                                name=name,
                            )

                            now_utc = dt_util.utcnow().timestamp()

                            fileName = Path(__file__).parent / (
                                BOARDING_PASSES_URI
                                + "/"
                                + getFileName(
                                    name + boardingPass["departure"]["dateUTC"]
                                )
                            )

                            nextDay = (
                                datetime.strptime(
                                    boardingPass["departure"]["dateUTC"],
                                    "%Y-%m-%dT%H:%M:%SZ",
                                )
                                + dt.timedelta(days=1)
                            ).timestamp()

                            if now_utc > nextDay:
                                if fileName and os.path.isfile(fileName):
                                    os.remove(fileName)
                            else:
                                sensors.append(
                                    RyanairBoardingPassImage(
                                        hass,
                                        boardPassCoordinator,
                                        boardingPass,
                                        boardingPass["pnr"],
                                        name,
                                        boardingPassDescription,
                                    )
                                )

    async_add_entities(sensors, update_before_add=True)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry created in the integrations UI."""

    config = hass.data[DOMAIN][entry.entry_id]
    # Update our config to include new repos and remove those that have been removed.
    await async_setup_platform(hass, config, async_add_entities)


class RyanairBoardingPassImage(
    CoordinatorEntity[RyanairBoardingPassCoordinator], ImageEntity
):
    """Representation of an image entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: RyanairBoardingPassCoordinator,
        boardingPassData: JsonObjectType,
        bookingRef: str,
        name: str,
        description: ImageEntityDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        ImageEntity.__init__(self, hass)
        self.bookingRef = bookingRef
        self.boardingPassData = boardingPassData

        flightNumber = (
            self.boardingPassData["flight"]["carrierCode"]
            + self.boardingPassData["flight"]["number"]
        )
        self._attr_device_info = deviceInfo(self.bookingRef + " " + flightNumber)
        self._attr_unique_id = f"Ryanair_boarding_pass-{flightNumber}-{self.bookingRef}-{name}-{description.key}".lower()

        self._attrs: dict[str, Any] = {}
        self.entity_description = description
        self._state = None
        self._name = name
        self._available = True
        self.access_tokens: dict[str, Any] = [""]
        self._current_qr_bytes: bytes | None = None

        if self.boardingPassData["paxType"] != "INF":
            fileName = (
                BOARDING_PASSES_URI
                + "/"
                + getFileName(self.name + self.boardingPassData["departure"]["dateUTC"])
            )
        else:
            fileName = "infant_qr.png"

        self.file_name = fileName

    async def _fetch_image(self) -> bytes:
        """Fetch the Image."""
        image_path = Path(__file__).parent / self.file_name
        return await self.hass.async_add_executor_job(image_path.read_bytes)

    async def async_image(self) -> bytes | None:
        """Return bytes of image."""

        qr_bytes = await self._fetch_image()

        if self._current_qr_bytes != qr_bytes:
            self._attr_image_last_updated = dt_util.utcnow()
            dt_now = dt_util.utcnow()
            self._attr_image_last_updated = dt_now
            self._current_qr_bytes = qr_bytes
            self.async_write_ha_state()

        return qr_bytes

    @property
    def icon(self) -> str:
        """Return a representative icon."""
        return "mdi:qrcode"

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    async def async_update(self) -> None:
        """Update the image entity data."""

        self._attr_image_last_updated = dt_util.utcnow()
