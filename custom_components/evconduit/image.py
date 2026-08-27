# custom_components/evconduit/image.py

"""Image platform exposing the vehicle's manufacturer artwork."""

import logging

from homeassistant.components.image import ImageEntity
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .sensor import _build_device_info

_LOGGER = logging.getLogger(__name__)


def _extract_image_url(data: dict | None) -> str | None:
    """Pull the artwork URL out of a vehicle status payload."""
    information = (data or {}).get("information") or {}
    url = information.get("imageUrl")
    return url or None


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the EVConduit vehicle image."""
    vehicle_coordinator = hass.data[DOMAIN].get(f"{entry.entry_id}_vehicle")

    if vehicle_coordinator is None:
        _LOGGER.error("Vehicle coordinator not found for image platform")
        return

    # Only Enode-sourced vehicles carry artwork. Creating the entity for a
    # vehicle that will never have an image would leave a permanently broken
    # picture in the dashboard, so skip it instead.
    if not _extract_image_url(vehicle_coordinator.data):
        _LOGGER.debug(
            "No vehicle image available for entry %s, skipping image entity",
            entry.entry_id,
        )
        return

    # The image is a nice-to-have. If this platform cannot start — an older core
    # with a different ImageEntity signature, say — the vehicle's sensors matter
    # far more, so degrade to no image rather than failing the config entry.
    try:
        entity = EVConduitVehicleImage(hass, vehicle_coordinator, entry)
    except Exception:
        _LOGGER.exception("Could not create the EVConduit vehicle image entity")
        return

    async_add_entities([entity])
    _LOGGER.debug("EVConduit vehicle image entity added")


class EVConduitVehicleImage(CoordinatorEntity, ImageEntity):
    """Manufacturer artwork for the linked vehicle.

    The URL is model-level art keyed on brand/model/year, not a render of the
    customer's actual car, so it changes only when the linked vehicle changes.
    """

    def __init__(self, hass, coordinator, entry):
        """Initialize the image entity."""
        CoordinatorEntity.__init__(self, coordinator)
        ImageEntity.__init__(self, hass)
        self._entry = entry
        self._attr_image_url = _extract_image_url(coordinator.data)
        self._attr_image_last_updated = dt_util.utcnow()

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info to link this entity to the EVConduit device."""
        return _build_device_info(self._entry, self.coordinator.data)

    @property
    def unique_id(self) -> str:
        """Return a unique ID for this image."""
        return f"{DOMAIN}-{self._entry.entry_id}-vehicle-image"

    @property
    def name(self) -> str:
        """Return the name of the image entity."""
        data = self.coordinator.data or {}
        vehicle_name = data.get("vehicleName")
        if vehicle_name:
            return f"{vehicle_name} Image"
        return "Vehicle Image"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Refresh the cached artwork when the vehicle's URL changes."""
        url = _extract_image_url(self.coordinator.data)

        # A poll that fails or a webhook push that omits `information` must not
        # blank out artwork we already have.
        if url and url != self._attr_image_url:
            self._attr_image_url = url
            self._cached_image = None
            self._attr_image_last_updated = dt_util.utcnow()

        super()._handle_coordinator_update()
