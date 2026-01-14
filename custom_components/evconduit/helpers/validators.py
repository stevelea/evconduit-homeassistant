import logging
from .api import EVConduitClient

_LOGGER = logging.getLogger(__name__)

async def validate_api_key(hass, api_key: str, base_url: str = "https://backend.evconduit.com") -> bool:
    """Validate API-key against EVConduit backend. Returns True/False."""
    try:
        client = EVConduitClient(hass, api_key, base_url, "dummy")
        _LOGGER.debug("[Validator] Created EVConduitClient for API key validation")
        userinfo = await client.async_get_userinfo()
        _LOGGER.debug(f"[Validator] Result from async_get_userinfo: {userinfo}")
        return bool(userinfo)
    except Exception as e:
        _LOGGER.exception(f"[Validator] Exception during API key validation: {e}")
        return False

async def validate_vehicle_id(hass, api_key: str, vehicle_id: str, base_url: str = "https://backend.evconduit.com") -> bool:
    """Validate vehicle_id by trying to fetch status. Returns True/False."""
    try:
        client = EVConduitClient(hass, api_key, base_url, vehicle_id)
        data = await client.async_get_vehicle_status()
        _LOGGER.debug(f"[Validator] Vehicle status fetched for id {vehicle_id}: {data}")
        return data is not None
    except Exception as e:
        _LOGGER.exception(f"[Validator] Exception during vehicle_id validation: {e}")
        return False
