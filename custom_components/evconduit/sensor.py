# custom_components/evconduit/sensor.py

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util
from .const import (
    DOMAIN, ICONS, USER_FIELDS, VEHICLE_FIELDS, WEBHOOK_FIELDS,
    CONF_CHARGING_HISTORY, CHARGING_HISTORY_LAST_SESSION_FIELDS,
    CHARGING_HISTORY_MONTHLY_FIELDS,
)
from datetime import datetime, timedelta, timezone
import logging
_LOGGER = logging.getLogger(__name__)


def _build_device_info(entry, vehicle_data: dict | None = None) -> DeviceInfo:
    """Build device_info using vehicle name and model from data."""
    if vehicle_data:
        name = vehicle_data.get("vehicleName")
        if not name:
            info = vehicle_data.get("information", {})
            name = info.get("displayName")
        if not name:
            info = vehicle_data.get("information", {})
            brand = info.get("brand", "")
            model = info.get("model", "")
            name = f"{brand} {model}".strip()

        info = vehicle_data.get("information", {})
        brand = info.get("brand", "")
        model_str = info.get("model", "")
        year = info.get("year")
        model_parts = [p for p in [brand, model_str] if p]
        model_display = " ".join(model_parts)
        if year:
            model_display = f"{model_display} ({year})" if model_display else str(year)
    else:
        name = None
        model_display = None

    return {
        "identifiers": {(DOMAIN, entry.entry_id)},
        "name": name or entry.title or "EVConduit",
        "manufacturer": "EVConduit",
        "model": model_display or "EVConduit Integration",
    }


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up EVConduit sensors."""
    user_coordinator = hass.data[DOMAIN].get(entry.entry_id)
    vehicle_coordinator = hass.data[DOMAIN].get(f"{entry.entry_id}_vehicle")

    entities = []

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
        entities.append(EVConduitSensor(user_coordinator, entry, field, label, unit, vehicle_coordinator))

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
        entities.append(EVConduitWebhookIdSensor(user_coordinator, entry, field, label, unit, vehicle_coordinator))

    # Charging history sensors (only if enabled in options)
    charging_history_enabled = entry.options.get(CONF_CHARGING_HISTORY, False)
    ch_coordinator = hass.data[DOMAIN].get(f"{entry.entry_id}_ch_coordinator")
    if charging_history_enabled and ch_coordinator:
        for field, (label, unit) in CHARGING_HISTORY_LAST_SESSION_FIELDS.items():
            entities.append(
                EVConduitChargingHistorySensor(
                    ch_coordinator, entry, field, label, unit, vehicle_coordinator
                )
            )
        for field, (label, unit) in CHARGING_HISTORY_MONTHLY_FIELDS.items():
            entities.append(
                EVConduitChargingHistorySensor(
                    ch_coordinator, entry, field, label, unit, vehicle_coordinator
                )
            )

    async_add_entities(entities)


class EVConduitSensor(CoordinatorEntity, SensorEntity):
    """Sensor for user information."""

    def __init__(self, coordinator, entry, field, name, unit, vehicle_coordinator=None):
        super().__init__(coordinator)
        self._entry = entry
        self._field = field
        self._name = name
        self._unit = unit
        self._vehicle_coordinator = vehicle_coordinator

    @property
    def device_info(self) -> DeviceInfo:
        vdata = self._vehicle_coordinator.data if self._vehicle_coordinator else None
        return _build_device_info(self._entry, vdata)

    @property
    def name(self):
        return self._name

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
        return _build_device_info(self._entry, self.coordinator.data)

    @property
    def name(self):
        return self._name

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
        return _build_device_info(self._entry, self.coordinator.data)

    @property
    def name(self) -> str:
        return "Location"

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
        loc = data.get("location") or {}
        return {
            "latitude":  loc.get("latitude"),
            "longitude": loc.get("longitude"),
        }

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}-{self._entry.entry_id}-location"

class EVConduitWebhookIdSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, entry, field, name, unit, vehicle_coordinator=None):
        super().__init__(coordinator)
        self._entry = entry
        self._field = field
        self._name = name
        self._unit = unit
        self._vehicle_coordinator = vehicle_coordinator

    @property
    def device_info(self) -> DeviceInfo:
        vdata = self._vehicle_coordinator.data if self._vehicle_coordinator else None
        return _build_device_info(self._entry, vdata)

    @property
    def name(self):
        return self._name

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
        return _build_device_info(self._entry, self.coordinator.data)

    @property
    def name(self):
        return "Last Seen Local"

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


class EVConduitChargingHistorySensor(CoordinatorEntity, SensorEntity):
    """Sensor for charging history data (last session and monthly aggregates)."""

    def __init__(self, coordinator, entry, field, name, unit, vehicle_coordinator=None):
        super().__init__(coordinator)
        self._entry = entry
        self._field = field
        self._name = name
        self._unit = unit
        self._vehicle_coordinator = vehicle_coordinator

    @property
    def device_info(self) -> DeviceInfo:
        vdata = self._vehicle_coordinator.data if self._vehicle_coordinator else None
        return _build_device_info(self._entry, vdata)

    @property
    def name(self):
        return self._name

    @property
    def icon(self):
        return ICONS.get(self._field)

    @property
    def unique_id(self):
        return f"{DOMAIN}-{self._entry.entry_id}-ch-{self._field}"

    @property
    def unit_of_measurement(self):
        return self._unit

    def _get_sessions(self) -> list:
        data = self.coordinator.data or {}
        return data.get("sessions", [])

    def _get_last_session(self) -> dict | None:
        sessions = self._get_sessions()
        if not sessions:
            return None
        # Sessions are appended oldest-first, so last element is most recent
        return sessions[-1]

    def _get_30_day_sessions(self) -> list:
        sessions = self._get_sessions()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        return [s for s in sessions if (s.get("start_time") or "") >= cutoff]

    @property
    def state(self):
        if self._field == "last_charge_energy":
            s = self._get_last_session()
            if not s:
                return None
            val = s.get("energy_added_kwh")
            return round(val, 2) if val is not None else None

        if self._field == "last_charge_cost":
            s = self._get_last_session()
            if not s:
                return None
            val = s.get("total_cost")
            return round(val, 2) if val is not None else None

        if self._field == "last_charge_location":
            s = self._get_last_session()
            if not s:
                return None
            return s.get("station_name") or "Unknown"

        if self._field == "last_charge_date":
            s = self._get_last_session()
            if not s:
                return None
            return s.get("start_time")

        if self._field == "last_charge_duration":
            s = self._get_last_session()
            if not s:
                return None
            start = s.get("start_time")
            end = s.get("end_time")
            if not start or not end:
                return None
            try:
                st = datetime.fromisoformat(start.replace("Z", "+00:00"))
                et = datetime.fromisoformat(end.replace("Z", "+00:00"))
                return round((et - st).total_seconds() / 60, 1)
            except (ValueError, TypeError):
                return None

        if self._field == "monthly_charge_energy":
            sessions = self._get_30_day_sessions()
            total = sum(s.get("energy_added_kwh") or 0 for s in sessions)
            return round(total, 2)

        if self._field == "monthly_charge_cost":
            sessions = self._get_30_day_sessions()
            total = sum(s.get("total_cost") or 0 for s in sessions)
            return round(total, 2)

        if self._field == "monthly_charge_count":
            return len(self._get_30_day_sessions())

        return None

    @property
    def extra_state_attributes(self):
        attrs = {}
        if self._field == "last_charge_cost":
            s = self._get_last_session()
            if s:
                attrs["currency"] = s.get("currency")
                attrs["cost_per_kwh"] = s.get("cost_per_kwh")
        elif self._field == "last_charge_energy":
            s = self._get_last_session()
            if s:
                attrs["battery_start"] = s.get("battery_level_start")
                attrs["battery_end"] = s.get("battery_level_end")
        elif self._field == "last_charge_location":
            s = self._get_last_session()
            if s:
                attrs["latitude"] = s.get("location_lat")
                attrs["longitude"] = s.get("location_lon")
        elif self._field == "monthly_charge_cost":
            sessions = self._get_30_day_sessions()
            if sessions:
                currencies = {s.get("currency") for s in sessions if s.get("currency")}
                attrs["currencies"] = list(currencies)
        elif self._field == "monthly_charge_count":
            all_sessions = self._get_sessions()
            attrs["total_sessions"] = len(all_sessions)
            # Last 20 sessions (most recent first) for Lovelace cards
            recent = list(reversed(all_sessions[-20:]))
            attrs["recent_sessions"] = [
                {
                    "date": s.get("start_time"),
                    "energy_kwh": round(s.get("energy_added_kwh") or 0, 2),
                    "cost": round(s.get("total_cost") or 0, 2),
                    "currency": s.get("currency"),
                    "location": s.get("station_name") or "Unknown",
                    "battery_start": s.get("battery_level_start"),
                    "battery_end": s.get("battery_level_end"),
                    "duration_min": self._calc_duration(s),
                }
                for s in recent
            ]
        return attrs

    @staticmethod
    def _calc_duration(session: dict) -> float | None:
        start = session.get("start_time")
        end = session.get("end_time")
        if not start or not end:
            return None
        try:
            st = datetime.fromisoformat(start.replace("Z", "+00:00"))
            et = datetime.fromisoformat(end.replace("Z", "+00:00"))
            return round((et - st).total_seconds() / 60, 1)
        except (ValueError, TypeError):
            return None
