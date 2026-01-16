# custom_components/evconduit/__init__.py

import logging
from datetime import timedelta
import voluptuous as vol
from aiohttp import web

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.components.webhook import async_register, async_unregister

from .const import (
    DOMAIN, ENVIRONMENTS,
    CONF_API_KEY, CONF_ENVIRONMENT, CONF_VEHICLE_ID, CONF_UPDATE_INTERVAL,
    CONF_ABRP_TOKEN, DEFAULT_UPDATE_INTERVAL,
)
from .api import EVConduitClient
from .abrp import ABRPClient

_LOGGER = logging.getLogger(__name__)


async def _handle_push_webhook(hass, webhook_id: str, request) -> web.Response:
    """Push webhook for EVConduit – updates the vehicle coordinator."""
    try:
        data = await request.json()
        _LOGGER.debug("Push payload: %s", data)

        coord = hass.data.get(DOMAIN, {}).get(f"{webhook_id}_vehicle")
        old = coord.data or {}

        # Ta endast vehicle-datan!
        vehicle_update = data.get("vehicle", {})
        if not vehicle_update:
            _LOGGER.warning("No 'vehicle' field in webhook payload, ignoring.")
            return web.Response(status=400, text="Missing vehicle data")
        
        # Start with a copy of the old values
        merged = old.copy()
        for key, val in vehicle_update.items():
            if isinstance(val, dict) and isinstance(old.get(key), dict):
                nested = old.get(key, {}).copy()
                nested.update(val)
                merged[key] = nested
            else:
                merged[key] = val

        # Submit the merged data
        coord.async_set_updated_data(merged)
        _LOGGER.debug("Manually updated evconduit vehicle status data")


        return web.Response(status=200, text="OK")

    except Exception:
        _LOGGER.exception("Error in push webhook handler")
        return web.Response(status=500, text="Error")

async def async_setup_entry(hass, entry) -> bool:
    """
    Set up EVConduit:
      • DataUpdateCoordinators (userinfo & vehicle status)
      • Charging-service
      • Push-webhook
    """
    _LOGGER.debug("Starting async_setup_entry for %s", entry.entry_id)

    try:
        # Read configuration
        api_key    = entry.data[CONF_API_KEY]
        env        = entry.data.get(CONF_ENVIRONMENT, "sandbox")
        vehicle_id = entry.data[CONF_VEHICLE_ID]
        base_url   = ENVIRONMENTS[env]
        vehicle_poll_minutes = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        _LOGGER.info("---- [EVConduit] async_setup_entry called ----")
        _LOGGER.info("Config: api_key=%s, env=%s, vehicle_id=%s, vehicle_poll_minutes=%s", api_key, env, vehicle_id, vehicle_poll_minutes)

        # Initialize API client
        client = EVConduitClient(hass, api_key, base_url, vehicle_id)
        _LOGGER.debug("EVConduitClient created")

        # 1) User info coordinator (refresh every 5 minutes)
        user_coord = DataUpdateCoordinator(
            hass, _LOGGER,
            name=f"{DOMAIN} user info",
            update_method=client.async_get_userinfo,
            update_interval=timedelta(minutes=vehicle_poll_minutes),
        )
        _LOGGER.debug("User DataUpdateCoordinator created (interval: %s min)", vehicle_poll_minutes)
        await user_coord.async_config_entry_first_refresh()

        # 2) Vehicle status coordinator (refresh every minute)
        vehicle_coord = DataUpdateCoordinator(
            hass, _LOGGER,
            name=f"{DOMAIN} vehicle status",
            update_method=client.async_get_vehicle_status,
            update_interval=timedelta(minutes=vehicle_poll_minutes),
        )
        _LOGGER.debug("Vehicle DataUpdateCoordinator created (interval: %s min)", vehicle_poll_minutes)
        await vehicle_coord.async_config_entry_first_refresh()

        # Store coordinators
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = user_coord
        hass.data[DOMAIN][f"{entry.entry_id}_vehicle"] = vehicle_coord
        _LOGGER.debug("Coordinators stored in hass.data for entry %s", entry.entry_id)

        # 2b) Set up ABRP integration if token is configured
        abrp_token = entry.data.get(CONF_ABRP_TOKEN, "")
        if abrp_token:
            from homeassistant.helpers.aiohttp_client import async_get_clientsession
            session = async_get_clientsession(hass)
            abrp_client = ABRPClient(session, abrp_token)
            hass.data[DOMAIN][f"{entry.entry_id}_abrp"] = abrp_client
            _LOGGER.info("ABRP integration enabled for entry %s", entry.entry_id)

            # Add listener to send telemetry on vehicle updates
            async def _send_abrp_update():
                """Send vehicle telemetry to ABRP when data updates."""
                if vehicle_coord.data:
                    await abrp_client.async_send_telemetry(vehicle_coord.data)

            vehicle_coord.async_add_listener(_send_abrp_update)
            _LOGGER.debug("ABRP update listener added to vehicle coordinator")

        # 3) Register charging service
        schema = vol.Schema({vol.Required("action"): vol.In(["START", "STOP"])})
        async def _handle_charging(call):
            action = call.data["action"]
            _LOGGER.debug("Service set_charging called with action=%s", action)
            try:
                result = await client.async_set_charging(action)
                if result:
                    _LOGGER.info("Charging %s executed successfully", action)
                else:
                    _LOGGER.error("Charging %s failed or returned None", action)
            except Exception as e:
                _LOGGER.exception("Error in set_charging service")

        hass.services.async_register(
            DOMAIN,
            "set_charging",
            _handle_charging,
            schema=schema,
        )
        _LOGGER.debug("Service set_charging registered")

        # 4) Register webhook under /api/webhook/{entry_id}
        webhook_id = entry.entry_id
        async_register(
            hass,
            DOMAIN,
            "EVConduit Push",
            webhook_id,
            _handle_push_webhook,
        )
        _LOGGER.debug("Webhook registered with id=%s", webhook_id)

        # 5) Register webhook with EVConduit backend (for Pro users)
        external_url = hass.config.external_url
        if external_url:
            registered = await client.async_register_webhook(webhook_id, external_url)
            if registered:
                _LOGGER.info("Webhook registered with EVConduit backend for push notifications")
            else:
                _LOGGER.warning("Failed to register webhook with EVConduit (Pro tier may be required)")
        else:
            _LOGGER.warning("No external_url configured in Home Assistant, skipping webhook registration")

        # Store client for unload
        hass.data[DOMAIN][f"{entry.entry_id}_client"] = client

        # 6) Forward to the sensor and device_tracker platforms
        await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "device_tracker"])
        _LOGGER.debug("Forwarded entry to sensor platform")

        _LOGGER.info("---- [EVConduit] async_setup_entry finished for %s ----", entry.entry_id)
        return True

    except Exception:
        _LOGGER.exception("Error setting up EVConduit integration")
        return False

async def async_unload_entry(hass, entry) -> bool:
    """Unload EVConduit: deregister webhook & service, remove coordinators."""
    _LOGGER.debug("Unloading EVConduit entry %s", entry.entry_id)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor", "device_tracker"])
    hass.services.async_remove(DOMAIN, "set_charging")
    async_unregister(hass, entry.entry_id)
    _LOGGER.debug("Service and webhook unregistered")

    # Unregister webhook from EVConduit backend
    client = hass.data.get(DOMAIN, {}).get(f"{entry.entry_id}_client")
    if client:
        try:
            await client.async_unregister_webhook()
            _LOGGER.info("Webhook unregistered from EVConduit backend")
        except Exception as e:
            _LOGGER.warning("Failed to unregister webhook from EVConduit: %s", e)

    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    hass.data.get(DOMAIN, {}).pop(f"{entry.entry_id}_vehicle", None)
    hass.data.get(DOMAIN, {}).pop(f"{entry.entry_id}_abrp", None)
    hass.data.get(DOMAIN, {}).pop(f"{entry.entry_id}_client", None)
    return unload_ok

# Lägg till denna!
async def async_reload_entry(hass, entry):
    """Reload EVConduit config entry when options are updated."""
    _LOGGER.info("---- [EVConduit] async_reload_entry called for %s ----", entry.entry_id)
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
    _LOGGER.info("---- [EVConduit] async_reload_entry finished for %s ----", entry.entry_id)
