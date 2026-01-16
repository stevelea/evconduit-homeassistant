# custom_components/evconduit/abrp.py

"""ABRP (A Better Route Planner) telemetry client."""

import logging
import time
import aiohttp

from .const import ABRP_API_URL

_LOGGER = logging.getLogger(__name__)


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

        # Build telemetry payload
        payload = {
            "token": self._token,
            "utc": int(time.time()),
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
