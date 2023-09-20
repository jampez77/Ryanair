"""Ryanair sensor platform."""
from datetime import timedelta
import logging
from aiohttp import ClientError
from homeassistant.core import HomeAssistant, callback
from typing import Any
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from .const import DOMAIN, CUSTOMER_ID
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
from .coordinator import RyanairProfileCoordinator, RyanairFlightsCoordinator

_LOGGER = logging.getLogger(__name__)
# Time between updating data from GitHub
SCAN_INTERVAL = timedelta(minutes=10)


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

    flightsDescription = SensorEntityDescription(
        key=f"Ryanair_flights{name}",
        name="Flights",
    )

    sensors = [
        RyanairProfileSensor(profileCoordinator, name, profileDescription),
        RyanairFlightsSensor(flightsCoordinator, name, flightsDescription),
    ]
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

    flightsDescription = SensorEntityDescription(
        key=f"Ryanair_flights{name}",
        name="Flights",
    )

    sensors = [
        RyanairProfileSensor(profileCoordinator, name, profileDescription),
        RyanairFlightsSensor(flightsCoordinator, name, flightsDescription),
    ]
    async_add_entities(sensors, update_before_add=True)


class RyanairFlightsSensor(CoordinatorEntity[RyanairFlightsCoordinator], SensorEntity):
    """Ryanair Flight sensor."""

    def __init__(
        self,
        coordinator: RyanairFlightsCoordinator,
        name: str,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)

        self.bookingRef = self.coordinator.data["items"][0]["rawBooking"][
            "recordLocator"
        ]

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"Ryanair_flights{name}")},
            manufacturer="Ryanair",
            name="ryanair_" + self.bookingRef,
            configuration_url="https://github.com/jampez77/Ryanair/",
        )
        self._attr_unique_id = f"Ryanair_flights{name}-{description.key}".lower()
        self.attrs: dict[str, Any] = {}
        self.entity_description = description
        self._state = None
        self._name = self.bookingRef
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
        return "mdi:airplane-takeoff"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.attrs

    async def async_update(self) -> None:
        """Update the entity.

        Only used by the generic entity update service.
        """
        try:
            flights = self.coordinator.data["items"][0]["rawBooking"]["flights"]
            seats = self.coordinator.data["items"][0]["rawBooking"]["seats"]
            passengers = self.coordinator.data["items"][0]["rawBooking"]["passengers"]

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

                flightDetails = {
                    "flightNumber": flight["flightNumber"],
                    "origin": flight["origin"],
                    "destination": flight["destination"],
                    "checkInOpenUTC": flight["checkInOpenUTC"],
                    "checkInCloseUTC": flight["checkInCloseUTC"],
                    "depart": flight["times"]["depart"],
                    "departUTC": flight["times"]["departUTC"],
                    "arrive": flight["times"]["arrive"],
                    "arriveUTC": flight["times"]["arriveUTC"],
                    "seats": flightSeats,
                }
                self.attrs[flight["journeyNum"]] = flightDetails

            self._state = str(self.coordinator.data["items"][0]["rawBooking"]["status"])
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
        self.attrs: dict[str, Any] = {}
        self.entity_description = description
        self._state = None
        self._name = (
            self.coordinator.data["firstName"] + " " + self.coordinator.data["lastName"]
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
        return self.coordinator.data["googlePictureUrl"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.attrs

    async def async_update(self) -> None:
        """Update the entity.

        Only used by the generic entity update service.
        """
        try:
            for key in self.coordinator.data:
                self.attrs[key] = self.coordinator.data[key]

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
