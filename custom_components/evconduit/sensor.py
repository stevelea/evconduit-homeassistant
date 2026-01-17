# custom_components/evconduit/sensor.py

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util
from .const import DOMAIN, ICONS, USER_FIELDS, VEHICLE_FIELDS, WEBHOOK_FIELDS
from datetime import datetime
import logging
_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up EVConduit sensors."""
    user_coordinator = hass.data[DOMAIN].get(entry.entry_id)
    vehicle_coordinator = hass.data[DOMAIN].get(f"{entry.entry_id}_vehicle")

    entities = []

    # Hämta capabilities från senaste vehicle-status
    vehicle_data = vehicle_coordinator.data or {}
    capabilities = vehicle_data.get("capabilities", {})
    _LOGGER.debug("[EVConduit] Vehicle capabilities: %s", capabilities)

    def is_field_capable(field):
        cap_key = field.split(".")[0]
        cap = capabilities.get(cap_key, {})
        is_cap = cap.get("isCapable", True)  # Default True för bakåtkompabilitet
        _LOGGER.debug("[EVConduit] Field '%s' capability '%s': %s", field, cap_key, is_cap)
        return is_cap

    # Userinfo sensors
    for field, (label, unit) in USER_FIELDS.items():
        entities.append(EVConduitSensor(user_coordinator, entry, field, label, unit))

    # Vehicle status sensors, nu med filtrering!
    if vehicle_coordinator:
        for field, (label, unit) in VEHICLE_FIELDS.items():
            if is_field_capable(field):
                entities.append(
                    EVConduitVehicleSensor(vehicle_coordinator, entry, field, label, unit)
                )
                _LOGGER.warning(
                    "[EVConduit] Sensor created: %s, field: %s",
                    f"{DOMAIN}-{entry.entry_id}-vehicle-{field}",
                    field,
                )
            else:
                _LOGGER.warning(
                    "[EVConduit] Skipping sensor for field '%s' since capability '%s' isCapable: False",
                    field, field.split(".")[0]
                )

    entities.append(
        EVConduitLocation(
            vehicle_coordinator,  # based on the status coordinator
            entry
        )
    )

    # Add Last Seen Local sensor (converts UTC to HA's local timezone)
    entities.append(
        EVConduitLastSeenLocalSensor(
            vehicle_coordinator,
            entry,
            hass
        )
    )

    for field, (label, unit) in WEBHOOK_FIELDS.items():
        entities.append(EVConduitWebhookIdSensor(user_coordinator, entry, field, label, unit))

    async_add_entities(entities)


class EVConduitSensor(CoordinatorEntity, SensorEntity):
    """Sensor for user information."""

    def __init__(self, coordinator, entry, field, name, unit):
        super().__init__(coordinator)
        self._entry = entry
        self._field = field
        self._name = name
        self._unit = unit

    @property
    def device_info(self) -> DeviceInfo:
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "EVConduit",
            "manufacturer": "Roger Aspelin",
            "model": "EVConduit Integration",
        }

    @property
    def name(self):
        return f"EVConduit {self._name}"

    @property
    def state(self):
        data = self.coordinator.data or {}
        return data.get(self._field)

    @property
    def unit_of_measurement(self):
        return self._unit

    @property
    def icon(self):
        return ICONS.get(self._field)

    @property
    def unique_id(self):
        # Fallback to entry_id if data is missing
        return f"{DOMAIN}-{self._entry.entry_id}-{self._field}"

class EVConduitVehicleSensor(CoordinatorEntity, SensorEntity):
    """Sensor for vehicle status."""

    def __init__(self, coordinator, entry, field, name, unit):
        super().__init__(coordinator)
        self._entry = entry
        self._field = field
        self._name = name
        self._unit = unit

    @property
    def device_info(self) -> DeviceInfo:
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "EVConduit",
            "manufacturer": "Roger Aspelin",
            "model": "EVConduit Integration",
        }

    @property
    def name(self):
        return f"EVConduit {self._name}"

    @property
    def state(self):
        # Retrieve the value from the nested JSON
        data = self.coordinator.data or {}
        parts = self._field.split(".")
        val = data
        for p in parts:
            if not isinstance(val, dict):
                val = None
                break
            val = val.get(p)

        # Special handling for null values on chargeRate and chargeTimeRemaining
        if self._field in ("chargeState.chargeRate", "chargeState.chargeTimeRemaining"):
            return "--" if val is None else val

        # Other sensors: return as usual (None → Unknown)
        return val

    @property
    def unit_of_measurement(self):
        return self._unit

    @property
    def icon(self):
        return ICONS.get(self._field)

    @property
    def unique_id(self):
        # Consistent id independent of response data
        return f"{DOMAIN}-{self._entry.entry_id}-vehicle-{self._field}"

class EVConduitLocation(CoordinatorEntity, SensorEntity):
    """Template sensor for vehicle position with lat/lon attributes."""

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "EVConduit",
            "manufacturer": "Roger Aspelin",
            "model": "EVConduit Integration",
        }

    @property
    def name(self) -> str:
        return "EVConduit Location"

    @property
    def state(self) -> str:
        """Use vehicleName as the state (or any field)."""
        data = self.coordinator.data or {}
        # vehicleName comes from /status/:vehicle_id
        return data.get("vehicleName") or "Unknown"

    @property
    def extra_state_attributes(self) -> dict:
        """Expose latitude/longitude as attributes."""
        data = self.coordinator.data or {}
        loc = data.get("location", {})
        return {
            "latitude":  loc.get("latitude"),
            "longitude": loc.get("longitude"),
        }

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}-{self._entry.entry_id}-location"

class EVConduitWebhookIdSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, entry, field, name, unit):
        super().__init__(coordinator)
        self._entry = entry
        self._field = field
        self._name = name
        self._unit = unit

    @property
    def device_info(self) -> DeviceInfo:
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "EVConduit",
            "manufacturer": "Roger Aspelin",
            "model": "EVConduit Integration",
        }

    @property
    def name(self):
        return f"EVConduit {self._name}"

    @property
    def state(self):
        # Returnera entry_id som är unikt för denna integration/instans.
        return self._entry.entry_id

    @property
    def unit_of_measurement(self):
        return self._unit

    @property
    def icon(self):
        return ICONS.get(self._field)

    @property
    def unique_id(self):
        # Fallback to entry_id if data is missing
        return f"{DOMAIN}-{self._entry.entry_id}-{self._field}"


class EVConduitLastSeenLocalSensor(CoordinatorEntity, SensorEntity):
    """Sensor that displays Last Seen time in Home Assistant's local timezone."""

    def __init__(self, coordinator, entry, hass):
        super().__init__(coordinator)
        self._entry = entry
        self._hass = hass

    @property
    def device_info(self) -> DeviceInfo:
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "EVConduit",
            "manufacturer": "Roger Aspelin",
            "model": "EVConduit Integration",
        }

    @property
    def name(self):
        return "EVConduit Last Seen Local"

    @property
    def state(self):
        """Convert UTC lastSeen to local timezone."""
        data = self.coordinator.data or {}
        last_seen_utc = data.get("lastSeen")

        if not last_seen_utc:
            return None

        try:
            # Parse the ISO 8601 UTC timestamp
            if last_seen_utc.endswith("Z"):
                last_seen_utc = last_seen_utc[:-1] + "+00:00"

            utc_dt = datetime.fromisoformat(last_seen_utc)

            # Convert to Home Assistant's local timezone
            local_dt = dt_util.as_local(utc_dt)

            # Format as human-readable string
            return local_dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception as e:
            _LOGGER.error("[EVConduit] Error converting lastSeen to local time: %s", e)
            return last_seen_utc

    @property
    def extra_state_attributes(self):
        """Include UTC time and timezone info as attributes."""
        data = self.coordinator.data or {}
        last_seen_utc = data.get("lastSeen")

        attrs = {
            "utc_time": last_seen_utc,
            "timezone": str(dt_util.DEFAULT_TIME_ZONE),
        }
        return attrs

    @property
    def icon(self):
        return ICONS.get("lastSeenLocal")

    @property
    def unique_id(self):
        return f"{DOMAIN}-{self._entry.entry_id}-vehicle-lastSeenLocal"
