"""Ryanair sensor platform."""
from datetime import timedelta
import logging
from aiohttp import ClientError
from homeassistant.core import HomeAssistant, callback
from typing import Any
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from .const import (
    DOMAIN,
    CUSTOMER_ID,
    ACCESS_DENIED,
    CAUSE,
    NOT_AUTHENTICATED,
    OPEN_TIME,
    CLOSE_TIME,
    TYPE
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)
from homeassistant.util import dt as dt_util
from datetime import datetime
from .coordinator import RyanairProfileCoordinator, RyanairFlightsCoordinator
from homeassistant.util.json import JsonObjectType
_LOGGER = logging.getLogger(__name__)
# Time between updating data from GitHub
SCAN_INTERVAL = timedelta(minutes=10)


def deviceInfo(bookingRef) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, f"Ryanair_{bookingRef}")},
        manufacturer="Ryanair",
        name=bookingRef,
        configuration_url="https://github.com/jampez77/Ryanair/",
    )


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

    name = entry.data[CUSTOMER_ID]

    profileDescription = SensorEntityDescription(
        key=f"Ryanair_{name}",
        name=f"Ryanair User Profile {name}",
    )

    flightsCoordinator = RyanairFlightsCoordinator(hass, session, config)

    await flightsCoordinator.async_refresh()

    name = config[CUSTOMER_ID]

    sensors = []

    if (ACCESS_DENIED not in profileCoordinator.data and CAUSE not in profileCoordinator.data and TYPE not in profileCoordinator.data):
        sensors.append(RyanairProfileSensor(
            profileCoordinator, name, profileDescription))

    if "items" in flightsCoordinator.data and len(flightsCoordinator.data["items"]) > 0:
        for item in flightsCoordinator.data["items"]:

            flights = item["rawBooking"]["flights"]
            bookingRef = item["rawBooking"]["recordLocator"]
            seats = item["rawBooking"]["seats"]
            passengers = item["rawBooking"]["passengers"]

            for flight in flights:
                flightSeats = []
                for seat in seats:
                    if seat["journeyNum"] == flight["journeyNum"]:
                        for passenger in passengers:
                            if seat["paxNum"] == passenger["paxNum"]:
                                flightSeats.append(
                                    passenger["firstName"]
                                    + " "
                                    + passenger["lastName"]
                                    + " ("
                                    + seat["code"]
                                    + ")"
                                )

                name = flight["flightNumber"] + \
                    " (" + flight["origin"] + " - " + \
                    flight["destination"] + ")"

                flightDescription = SensorEntityDescription(
                    key=f"Ryanair_flight{name}",
                    name=name,
                )
                sensors.append(RyanairFlightSensor(
                    flightsCoordinator, bookingRef, flight, flightSeats, name, flightDescription))

    async_add_entities(sensors, update_before_add=True)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    _: DiscoveryInfoType | None = None,
) -> None:
    """Set up the sensor platform."""
    session = async_get_clientsession(hass)

    profileCoordinator = RyanairProfileCoordinator(hass, session, config)

    name = config[CUSTOMER_ID]

    profileDescription = SensorEntityDescription(
        key=f"Ryanair_{name}",
        name="User Profile",
    )

    flightsCoordinator = RyanairFlightsCoordinator(hass, session, config)

    name = config[CUSTOMER_ID]

    sensors = []

    if (ACCESS_DENIED not in profileCoordinator.data and CAUSE not in profileCoordinator.data and TYPE not in profileCoordinator.data):
        sensors.append(RyanairProfileSensor(
            profileCoordinator, name, profileDescription))

    if "items" in flightsCoordinator.data and len(flightsCoordinator.data["items"]) > 0:
        for item in flightsCoordinator.data["items"]:

            flights = item["rawBooking"]["flights"]
            bookingRef = item["rawBooking"]["recordLocator"]
            seats = item["rawBooking"]["seats"]
            passengers = item["rawBooking"]["passengers"]

            for flight in flights:
                flightSeats = []
                for seat in seats:
                    if seat["journeyNum"] == flight["journeyNum"]:
                        for passenger in passengers:
                            if seat["paxNum"] == passenger["paxNum"]:
                                flightSeats.append(
                                    passenger["firstName"]
                                    + " "
                                    + passenger["lastName"]
                                    + " ("
                                    + seat["code"]
                                    + ")"
                                )

                name = flight["flightNumber"] + \
                    " (" + flight["origin"] + " - " + \
                    flight["destination"] + ")"

                flightDescription = SensorEntityDescription(
                    key=f"Ryanair_flight{name}",
                    name=name,
                )
                sensors.append(RyanairFlightSensor(
                    flightsCoordinator, bookingRef, flight, flightSeats, name, flightDescription))

    async_add_entities(sensors, update_before_add=True)


class RyanairFlightSensor(CoordinatorEntity[RyanairFlightsCoordinator], SensorEntity):
    """Ryanair Check In Sensor"""

    def __init__(
        self,
        coordinator: RyanairFlightsCoordinator,
        bookingRef: str,
        flight: JsonObjectType,
        seats: JsonObjectType,
        name: str,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.bookingRef = bookingRef
        self.flight = flight
        self._attr_device_info = deviceInfo(self.bookingRef)
        self._attr_unique_id = f"Ryanair_flight{self.bookingRef}-{name}-{description.key}".lower()
        self._attrs: dict[str, Any] = {}
        self.entity_description = description
        self._state = None
        self._name = name
        self._available = True
        self.seats = seats

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._name

    @property
    def unique_id(self) -> str:
        """Return the unique ID of the sensor."""
        return self._attr_unique_id

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    @property
    def native_value(self) -> str:
        return self._state

    @property
    def icon(self) -> str:
        """Return a representative icon."""
        return "mdi:airplane-takeoff"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:

        attrs = {
            "flightNumber": self.flight["flightNumber"],
            "origin": self.flight["origin"],
            "destination": self.flight["destination"],
            "arrive": self.flight["times"]["arriveUTC"],
            "depart": self.flight["times"]["departUTC"],
            "checkInOpen": self.flight["checkInOpenUTC"],
            "checkInClose": self.flight["checkInCloseUTC"],
            "checkInFreeAllocateOpen": self.flight["checkInFreeAllocateOpenUtcDate"],
            "isCancelled": self.flight["segments"][0]["isCancelled"],
            "seats": self.seats
        }

        self._attrs = attrs
        return self._attrs

    async def async_update(self) -> None:
        """Update the entity.

        Only used by the generic entity update service.
        """
        try:

            now_utc = dt_util.utcnow().timestamp()

            checkInOpenUTC = datetime.strptime(
                self.flight["checkInOpenUTC"], "%Y-%m-%dT%H:%M:%SZ").timestamp()

            checkInCloseUTC = datetime.strptime(
                self.flight["checkInCloseUTC"], "%Y-%m-%dT%H:%M:%SZ").timestamp()

            if now_utc < checkInOpenUTC:
                state = "Check in not open"
            elif now_utc >= checkInOpenUTC and now_utc <= checkInCloseUTC:
                state = "Check in open"
            else:
                state = "Check in closed"

            self._state = state
            self._available = True
        except ClientError:
            self._available = False
            _LOGGER.exception(
                "Error retrieving data from Ryanair for sensor %s", self.name
            )


class RyanairProfileSensor(CoordinatorEntity[RyanairProfileCoordinator], SensorEntity):
    """Define an Ryanair sensor."""

    def __init__(
        self,
        coordinator: RyanairProfileCoordinator,
        name: str,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"Ryanair_{name}")},
            manufacturer="Ryanair",
            name=self.coordinator.data["firstName"]
            + " "
            + self.coordinator.data["lastName"],
            configuration_url="https://github.com/jampez77/Ryanair/",
        )
        self._attr_unique_id = f"Ryanair_{name}-{description.key}".lower()
        self._attrs: dict[str, Any] = {}
        self.entity_description = description
        self._state = None
        self._name = (
            self.coordinator.data["firstName"] +
            " " + self.coordinator.data["lastName"]
        )
        self._available = True

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._name

    @property
    def unique_id(self) -> str:
        """Return the unique ID of the sensor."""
        return self._attr_unique_id

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    @property
    def native_value(self) -> str:
        return self._state

    @property
    def icon(self) -> str:
        """Return a representative icon."""
        return "mdi:account"

    @property
    def entity_picture(self) -> str:
        """Return a representative icon."""
        if "googlePictureUrl" in self.coordinator.data:
            return self.coordinator.data["googlePictureUrl"]
        else:
            return self._attr_entity_picture

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        for key in self.coordinator.data:
            self._attrs[key] = self.coordinator.data[key]
        return self._attrs

    async def async_update(self) -> None:
        """Update the entity.

        Only used by the generic entity update service.
        """
        try:
            self._state = str(self.coordinator.data["email"])
            self._available = True
        except ClientError:
            self._available = False
            _LOGGER.exception(
                "Error retrieving data from Ryanair for sensor %s", self.name
            )


class RyanairEntity(CoordinatorEntity, SensorEntity):
    """An entity using CoordinatorEntity."""

    def __init__(self, coordinator, idx) -> None:
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator, context=idx)
        self.idx = idx

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return self.entity_description.attr_fn(self)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle data update."""

        self.async_write_ha_state()
