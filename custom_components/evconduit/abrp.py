# custom_components/evconduit/abrp.py

"""ABRP (A Better Route Planner) telemetry client."""

import logging
import time
from datetime import datetime, timezone

import aiohttp

from .const import ABRP_API_URL

_LOGGER = logging.getLogger(__name__)


def _epoch_from_iso(value) -> int | None:
    """Parse a payload timestamp into the epoch seconds ABRP's API wants.

    Tolerates both the "Z" that Enode sends and the "+00:00" that the backend
    writes, and treats a naive timestamp as UTC rather than guessing a local
    zone.
    """
    if not isinstance(value, str) or not value.strip():
        return None

    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return int(parsed.timestamp())


class ABRPClient:
    """Client for sending telemetry to ABRP."""

    def __init__(self, session: aiohttp.ClientSession, token: str):
        """Initialize ABRP client."""
        self._session = session
        self._token = token

    def _get_nested(self, data: dict, path: str, default=None):
        """Get a nested value from a dict using dot notation."""
        keys = path.split(".")
        value = data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return default
            if value is None:
                return default
        return value

    async def async_send_telemetry(self, vehicle_data: dict) -> bool:
        """Send vehicle telemetry to ABRP.

        Returns True if successful, False otherwise.
        """
        if not vehicle_data:
            _LOGGER.debug("No vehicle data to send to ABRP")
            return False

        # The reading's own time, not the time we happen to be sending it.
        # Stamping "now" on a value read hours ago is what let a car asleep for
        # the night report its last known state of charge as a current one, and
        # ABRP has no way to tell the difference — so the timestamp has to be
        # the reading's, and ABRP can then judge the age for itself.
        payload = {
            "token": self._token,
            "utc": _epoch_from_iso(self._get_nested(vehicle_data, "lastSeen"))
            or int(time.time()),
        }

        # Map EVConduit fields to ABRP fields
        soc = self._get_nested(vehicle_data, "chargeState.batteryLevel")
        if soc is not None:
            payload["soc"] = soc

        lat = self._get_nested(vehicle_data, "location.latitude")
        if lat is not None:
            payload["lat"] = lat

        lon = self._get_nested(vehicle_data, "location.longitude")
        if lon is not None:
            payload["lon"] = lon

        is_charging = self._get_nested(vehicle_data, "chargeState.isCharging")
        if is_charging is not None:
            payload["is_charging"] = 1 if is_charging else 0

        power = self._get_nested(vehicle_data, "chargeState.chargeRate")
        if power is not None:
            payload["power"] = power

        # SOC is required for ABRP
        if "soc" not in payload:
            _LOGGER.debug("No SOC data available, skipping ABRP update")
            return False

        try:
            _LOGGER.debug("Sending telemetry to ABRP: %s", payload)
            async with self._session.post(
                ABRP_API_URL,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ) as response:
                if response.status == 200:
                    _LOGGER.debug("ABRP telemetry sent successfully")
                    return True
                else:
                    text = await response.text()
                    _LOGGER.warning(
                        "ABRP telemetry failed with status %s: %s",
                        response.status,
                        text,
                    )
                    return False
        except aiohttp.ClientError as err:
            _LOGGER.warning("Failed to send ABRP telemetry: %s", err)
            return False
        except Exception:
            _LOGGER.exception("Unexpected error sending ABRP telemetry")
            return False
