"""
EVConduit API client for fetching user and vehicle information and 
handling rate‐limit (HTTP 429) with persistent notifications.
"""
from datetime import datetime
import aiohttp
import logging

from homeassistant.helpers.update_coordinator import UpdateFailed

_LOGGER = logging.getLogger(__name__)

class EVConduitClient:
    """
    HTTP client to interact with EVConduit backend.

    Args:
      hass: Home Assistant core instance (for notifications).
      api_key (str): Bearer token.
      base_url (str): Base URL of the EVConduit API.
      vehicle_id (str): ID of the vehicle for status/charge endpoints.
    """
    def __init__(self, hass, api_key: str, base_url: str, vehicle_id: str):
        self.hass       = hass
        self.api_key    = api_key
        self.base_url   = base_url.rstrip("/")
        self.vehicle_id = vehicle_id

    async def async_get_userinfo(self) -> dict | None:
        url = f"{self.base_url}/api/me"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        _LOGGER.debug(f"[EVConduitClient] GET userinfo: {url}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        _LOGGER.debug(f"[EVConduitClient] Userinfo: {data}")
                        return data

                    _LOGGER.error(f"[EVConduitClient] Failed userinfo: HTTP {resp.status}")
        except Exception as err:
            _LOGGER.exception(f"[EVConduitClient] Exception fetching userinfo: {err}")
        return None

    async def async_get_vehicle_status(self) -> dict:
        """
        Fetch full status for the configured vehicle.
        Raises UpdateFailed on rate‐limit (429) to skip this cycle.
        """
        _LOGGER.info("Polling vehicle status at %s", datetime.now())
        url = f"{self.base_url}/api/status/{self.vehicle_id}"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        _LOGGER.debug(f"[EVConduitClient] GET vehicle status: {url}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        _LOGGER.debug(f"[EVConduitClient] Vehicle status: {data}")
                        return data

                    if resp.status == 429:
                        _LOGGER.warning(f"[EVConduitClient] Rate limited (429) on {url}")
                        self.hass.async_create_task(
                            self.hass.services.async_call(
                                "persistent_notification",
                                "create",
                                {
                                    "title": "EVConduit Rate Limit",
                                    "message": (
                                        f"Rate limit hit for vehicle {self.vehicle_id}. "
                                        "Skipping this update."
                                    ),
                                },
                            )
                        )
                        raise UpdateFailed("429 rate limited by EVConduit")
                    
                    # Bad request (e.g. invalid vehicle_id, backend error, etc)
                    if resp.status == 400:
                        text = await resp.text()
                        _LOGGER.warning(f"[EVConduitClient] Vehicle status fetch rejected (400): {text}")
                        self.hass.async_create_task(
                            self.hass.services.async_call(
                                "persistent_notification",
                                "create",
                                {
                                    "title": "EVConduit Vehicle Status Error",
                                    "message": (
                                        f"Vehicle status request rejected for vehicle {self.vehicle_id}. "
                                        f"Error: {text}"
                                    ),
                                },
                            )
                        )
                        raise UpdateFailed(f"400 Bad Request: {text}")

                    # Other errors - raise UpdateFailed to preserve previous data
                    text = await resp.text()
                    _LOGGER.error(f"[EVConduitClient] Vehicle status fetch failed HTTP {resp.status}: {text}")
                    raise UpdateFailed(f"HTTP {resp.status}: {text}")

        except UpdateFailed:
            # Re-raise UpdateFailed so coordinator preserves previous data
            raise
        except Exception as err:
            _LOGGER.exception(f"[EVConduitClient] Exception fetching vehicle status: {err}")
            raise UpdateFailed(f"Exception: {err}")

    async def async_set_charging(self, action: str) -> dict | None:
        url = f"{self.base_url}/api/charging/{self.vehicle_id}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"action": action.upper()}
        _LOGGER.debug(f"[EVConduitClient] POST charging: {url} payload={payload}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, timeout=15) as resp:
                    text = await resp.text()
                    if resp.status in (200, 201):
                        data = await resp.json()
                        _LOGGER.debug(f"[EVConduitClient] Charging response: {data}")
                        return data
                    _LOGGER.error(
                        f"[EVConduitClient] Charging failed HTTP {resp.status}: {text}"
                    )
        except Exception as err:
            _LOGGER.exception(f"[EVConduitClient] Exception setting charging: {err}")
        return None

    async def async_get_vehicles(self) -> list[dict]:
        """
        Fetch all vehicles linked to the current user.
        Returns a list of dicts (id, displayName, model, etc), or empty list.
        """
        url = f"{self.base_url}/api/user/vehicles"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        _LOGGER.debug(f"[EVConduitClient] GET vehicles: {url}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        _LOGGER.debug(f"[EVConduitClient] Vehicles: {data}")
                        # Expects: [{"id": "...", "displayName": "...", ...}, ...]
                        return data if isinstance(data, list) else []
                    _LOGGER.error(f"[EVConduitClient] Failed to get vehicles: HTTP {resp.status}")
        except Exception as err:
            _LOGGER.exception(f"[EVConduitClient] Exception fetching vehicles: {err}")
        return []

    async def async_register_webhook(self, webhook_id: str, external_url: str) -> bool:
        """
        Register the Home Assistant webhook URL with EVConduit.
        This enables push notifications for real-time vehicle updates.
        Returns True if successful, False otherwise.
        """
        url = f"{self.base_url}/api/ha/webhook/register"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "webhook_id": webhook_id,
            "external_url": external_url.rstrip("/"),
        }
        _LOGGER.debug(f"[EVConduitClient] POST webhook register: {url}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        _LOGGER.info(f"[EVConduitClient] Webhook registered successfully: {data}")
                        return True
                    elif resp.status == 403:
                        text = await resp.text()
                        _LOGGER.warning(f"[EVConduitClient] Webhook registration denied (Pro tier required): {text}")
                        return False
                    else:
                        text = await resp.text()
                        _LOGGER.error(f"[EVConduitClient] Webhook registration failed HTTP {resp.status}: {text}")
                        return False
        except Exception as err:
            _LOGGER.exception(f"[EVConduitClient] Exception registering webhook: {err}")
        return False

    async def async_unregister_webhook(self) -> bool:
        """
        Unregister the Home Assistant webhook URL from EVConduit.
        Returns True if successful, False otherwise.
        """
        url = f"{self.base_url}/api/ha/webhook/register"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        _LOGGER.debug(f"[EVConduitClient] DELETE webhook unregister: {url}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.delete(url, headers=headers, timeout=15) as resp:
                    if resp.status == 200:
                        _LOGGER.info("[EVConduitClient] Webhook unregistered successfully")
                        return True
                    else:
                        text = await resp.text()
                        _LOGGER.error(f"[EVConduitClient] Webhook unregister failed HTTP {resp.status}: {text}")
                        return False
        except Exception as err:
            _LOGGER.exception(f"[EVConduitClient] Exception unregistering webhook: {err}")
        return False

    async def async_update_odometer(self, odometer_km: float) -> dict | None:
        """
        Update the odometer reading for the latest charging session.
        This allows Home Assistant to push odometer readings from OBD or other sources.
        Returns the response dict if successful, None otherwise.
        """
        url = f"{self.base_url}/api/ha/charging/{self.vehicle_id}/odometer"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"odometer_km": odometer_km}
        _LOGGER.debug(f"[EVConduitClient] POST odometer update: {url} payload={payload}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        _LOGGER.info(f"[EVConduitClient] Odometer updated successfully: {data}")
                        return data
                    elif resp.status == 404:
                        text = await resp.text()
                        _LOGGER.warning(f"[EVConduitClient] No charging session found to update: {text}")
                        return None
                    else:
                        text = await resp.text()
                        _LOGGER.error(f"[EVConduitClient] Odometer update failed HTTP {resp.status}: {text}")
                        return None
        except Exception as err:
            _LOGGER.exception(f"[EVConduitClient] Exception updating odometer: {err}")
        return None

