# custom_components/evconduit/device_tracker.py

import logging
from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up EVConduit device tracker."""
    vehicle_coordinator = hass.data[DOMAIN].get(f"{entry.entry_id}_vehicle")

    if vehicle_coordinator is None:
        _LOGGER.error("Vehicle coordinator not found for device tracker")
        return

    async_add_entities([EVConduitDeviceTracker(vehicle_coordinator, entry)])
    _LOGGER.debug("EVConduit device tracker entity added")


class EVConduitDeviceTracker(CoordinatorEntity, TrackerEntity):
    """Device tracker for EVConduit vehicle location."""

    def __init__(self, coordinator, entry):
        """Initialize the device tracker."""
        super().__init__(coordinator)
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info to link this entity to the EVConduit device."""
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "EVConduit",
            "manufacturer": "Roger Aspelin",
            "model": "EVConduit Integration",
        }

    @property
    def unique_id(self) -> str:
        """Return a unique ID for this tracker."""
        return f"{DOMAIN}-{self._entry.entry_id}-device-tracker"

    @property
    def name(self) -> str:
        """Return the name of the tracker."""
        data = self.coordinator.data or {}
        vehicle_name = data.get("vehicleName")
        if vehicle_name:
            return f"{vehicle_name}"
        return "EVConduit Vehicle"

    @property
    def latitude(self) -> float | None:
        """Return latitude value of the device."""
        data = self.coordinator.data or {}
        location = data.get("location", {})
        return location.get("latitude")

    @property
    def longitude(self) -> float | None:
        """Return longitude value of the device."""
        data = self.coordinator.data or {}
        location = data.get("location", {})
        return location.get("longitude")

    @property
    def source_type(self) -> SourceType:
        """Return the source type of the device tracker."""
        return SourceType.GPS

    @property
    def icon(self) -> str:
        """Return the icon for the tracker."""
        return "mdi:car"
