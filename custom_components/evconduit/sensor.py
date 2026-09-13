# custom_components/evconduit/sensor.py

from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_registry import RegistryEntryDisabler
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util
from .const import (
    DOMAIN, ICONS, USER_FIELDS, VEHICLE_FIELDS, WEBHOOK_FIELDS,
    NEVER_SUPPLIED_FIELDS, ENODE_ONLY_FIELDS,
    CONF_CHARGING_HISTORY, CHARGING_HISTORY_LAST_SESSION_FIELDS,
    CHARGING_HISTORY_MONTHLY_FIELDS,
)
from datetime import datetime, timedelta, timezone
import logging
_LOGGER = logging.getLogger(__name__)


# Fields where a value we derive ourselves is more trustworthy than the one the
# data source reports. The vendor's model year is frequently wrong — Enode
# returns the same year for every car of a model regardless of build date —
# whereas VIN position 10 encodes it directly.
PREFERRED_FIELDS = {
    "information.year": "information.vinModelYear",
}


def _resolve_field(data: dict | None, field: str):
    """Read a dotted path out of a nested payload."""
    value = data or {}
    for part in field.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _preferred_value(data: dict | None, field: str):
    """Return the derived value for a field when we have one, else the reported one."""
    preferred = PREFERRED_FIELDS.get(field)
    if preferred is not None:
        derived = _resolve_field(data, preferred)
        if derived is not None:
            return derived
    return _resolve_field(data, field)


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
        year = _preferred_value(vehicle_data, "information.year")
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


def _unfillable_fields(vehicle_data: dict) -> set:
    """The fields this particular vehicle can never supply.

    Two different reasons, which are handled the same way but mean different
    things:

    * NEVER_SUPPLIED_FIELDS — no source has ever sent them, so no vehicle can
      fill them and they stay disabled however the car is connected.
    * ENODE_ONLY_FIELDS on an ABRP-fed car — the ABRP feed has none of them.
      Presence is checked as well as the source, because a car linked through
      both Enode and ABRP has those values copied onto its ABRP row, and that
      data is real: only fields that are genuinely absent are switched off.
    """
    unfillable = set(NEVER_SUPPLIED_FIELDS)

    source = (vehicle_data.get("source") or "").lower()
    if source == "abrp":
        for field in ENODE_ONLY_FIELDS:
            if _resolve_field(vehicle_data, field) is None:
                unfillable.add(field)

    return unfillable


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up EVConduit sensors."""
    user_coordinator = hass.data[DOMAIN].get(entry.entry_id)
    vehicle_coordinator = hass.data[DOMAIN].get(f"{entry.entry_id}_vehicle")

    entities = []

    vehicle_data = vehicle_coordinator.data or {}
    capabilities = vehicle_data.get("capabilities", {})
    _LOGGER.debug("[EVConduit] Vehicle capabilities: %s", capabilities)

    # Which sensors this vehicle can never fill. They are still created — a
    # source may start supplying them later — but registered disabled, so they
    # do not sit at "unknown" on a dashboard that cannot use them.
    unfillable = _unfillable_fields(vehicle_data)
    source_only = unfillable - NEVER_SUPPLIED_FIELDS
    if source_only:
        _LOGGER.info(
            "[EVConduit] Vehicle source is %r, so these sensors start disabled: %s",
            vehicle_data.get("source"),
            sorted(source_only),
        )

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
                    EVConduitVehicleSensor(
                        vehicle_coordinator, entry, field, label, unit, unfillable
                    )
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

    # entity_registry_enabled_default is applied when a sensor is first
    # registered, so an install that has been running since before this change
    # keeps them enabled and showing "unknown". Registration is scheduled rather
    # than finished, hence the delay before looking.
    async_call_later(hass, 5, _reconcile_disabled_sensors(hass, entry, unfillable))


def _reconcile_disabled_sensors(hass, entry, unfillable):
    """A one-shot callback that brings registered sensors in line with the vehicle.

    Two jobs, because the registry outlives a single setup:

    * Switch off a sensor the vehicle cannot fill, but only while it has still
      never produced a value — so a sensor that a source does fill is left alone.
    * Switch back on one this integration had previously switched off, if the
      vehicle can fill it now. Only our own doing is undone: an entity a user
      disabled carries RegistryEntryDisabler.USER and is never touched.

    Nothing can tell a hand-enabled sensor from a default one, so a sensor the
    vehicle cannot fill and a user switches back on is switched off again on the
    next restart. That is the honest cost of not leaving them cluttering every
    dashboard.
    """
    restorable = ENODE_ONLY_FIELDS - unfillable

    @callback
    def _run(now=None):
        try:
            registry = er.async_get(hass)
            for field in unfillable:
                _disable_when_unused(registry, hass, entry, field)
            for field in restorable:
                _restore_when_we_disabled_it(registry, entry, field)
        except Exception:
            _LOGGER.exception("[EVConduit] Could not reconcile disabled sensors")

    return _run


def _entity_id_for(registry, entry, field):
    """The registry entity id for one vehicle-status field, if it is registered."""
    unique_id = f"{DOMAIN}-{entry.entry_id}-vehicle-{field}"
    return registry.async_get_entity_id("sensor", DOMAIN, unique_id)


def _disable_when_unused(registry, hass, entry, field):
    entity_id = _entity_id_for(registry, entry, field)
    if not entity_id:
        return

    registered = registry.async_get(entity_id)
    if not registered or registered.disabled_by is not None:
        return

    state = hass.states.get(entity_id)
    if state is not None and state.state not in ("unknown", "unavailable"):
        return

    registry.async_update_entity(entity_id, disabled_by=RegistryEntryDisabler.INTEGRATION)
    _LOGGER.info("[EVConduit] Disabled %s: this vehicle cannot supply it", entity_id)


def _restore_when_we_disabled_it(registry, entry, field):
    entity_id = _entity_id_for(registry, entry, field)
    if not entity_id:
        return

    registered = registry.async_get(entity_id)
    if not registered or registered.disabled_by != RegistryEntryDisabler.INTEGRATION:
        return

    registry.async_update_entity(entity_id, disabled_by=None)
    _LOGGER.info("[EVConduit] Enabled %s: this vehicle can supply it", entity_id)


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

    def __init__(self, coordinator, entry, field, name, unit, unfillable=frozenset()):
        super().__init__(coordinator)
        self._entry = entry
        self._field = field
        self._name = name
        self._unit = unit
        # A sensor for a field this vehicle can never supply is registered
        # disabled, so it does not clutter a dashboard with a permanent
        # "unknown". It is still there to be enabled by anyone who wants to
        # watch for it.
        self._attr_entity_registry_enabled_default = field not in unfillable

    @property
    def device_info(self) -> DeviceInfo:
        return _build_device_info(self._entry, self.coordinator.data)

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        # Retrieve the value from the nested JSON, preferring a derived value
        # over the reported one where we have a better source (see
        # PREFERRED_FIELDS).
        data = self.coordinator.data or {}
        val = _preferred_value(data, self._field)

        # Special handling for null values on chargeRate and chargeTimeRemaining
        if self._field in ("chargeState.chargeRate", "chargeState.chargeTimeRemaining"):
            return "--" if val is None else val

        # Other sensors: return as usual (None → Unknown)
        return val

    @property
    def extra_state_attributes(self):
        """Expose the reported value alongside a derived one, so nothing is lost."""
        preferred = PREFERRED_FIELDS.get(self._field)
        if preferred is None:
            return None

        data = self.coordinator.data or {}
        derived = _resolve_field(data, preferred)
        reported = _resolve_field(data, self._field)
        if derived is None:
            return {"value_source": "vendor"}

        return {
            "value_source": "vin",
            "reported_by_source": reported,
        }

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
