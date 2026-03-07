# custom_components/evconduit/__init__.py

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
import voluptuous as vol
from aiohttp import web

from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.storage import Store
from homeassistant.components.webhook import async_register, async_unregister

from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval

from .const import (
    DOMAIN, ENVIRONMENTS,
    CONF_API_KEY, CONF_ENVIRONMENT, CONF_VEHICLE_ID, CONF_UPDATE_INTERVAL,
    CONF_ABRP_TOKEN, CONF_ODOMETER_ENTITY, CONF_ELECTRICITY_RATE_ENTITY,
    CONF_ELECTRICITY_RATE_CURRENCY, CONF_CHARGING_HISTORY,
    DEFAULT_UPDATE_INTERVAL, CHARGING_HISTORY_SYNC_INTERVAL,
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
        if not coord:
            _LOGGER.warning("No vehicle coordinator found for webhook_id=%s", webhook_id)
            return web.Response(status=404, text="No coordinator")
        old = coord.data or {}

        vehicle_update = data.get("vehicle", {})
        if not vehicle_update:
            _LOGGER.warning("No 'vehicle' field in webhook payload, ignoring.")
            return web.Response(status=400, text="Missing vehicle data")

        # Get the configured vehicle_id from the entry
        # Users may have configured with either the Enode ID or the internal DB ID,
        # so check against all IDs provided by the backend.
        entry = hass.config_entries.async_get_entry(webhook_id)
        if entry:
            configured_vehicle_id = entry.data.get(CONF_VEHICLE_ID)
            incoming_ids = {
                vehicle_update.get("id"),
                vehicle_update.get("enodeId"),
                data.get("enodeVehicleId"),
                data.get("internalVehicleId"),
                data.get("vehicleId"),
            }
            incoming_ids.discard(None)
            if configured_vehicle_id and incoming_ids and configured_vehicle_id not in incoming_ids:
                _LOGGER.debug(
                    "Ignoring webhook for different vehicle: configured=%s, incoming=%s",
                    configured_vehicle_id,
                    incoming_ids,
                )
                return web.Response(status=200, text="OK (ignored - different vehicle)")

        # Log incoming chargeState for debugging
        incoming_charge_state = vehicle_update.get("chargeState", {})
        old_charge_state = old.get("chargeState", {})
        _LOGGER.info(
            "Webhook chargeState - incoming chargeRate: %s, old chargeRate: %s, incoming batteryLevel: %s",
            incoming_charge_state.get("chargeRate"),
            old_charge_state.get("chargeRate"),
            incoming_charge_state.get("batteryLevel"),
        )

        # Start with a copy of the old values
        merged = old.copy()
        for key, val in vehicle_update.items():
            if isinstance(val, dict) and isinstance(old.get(key), dict):
                nested = old.get(key, {}).copy()
                nested.update(val)
                merged[key] = nested
            else:
                merged[key] = val

        # Log merged chargeState for debugging
        merged_charge_state = merged.get("chargeState", {})
        _LOGGER.info(
            "Merged chargeState - chargeRate: %s, batteryLevel: %s",
            merged_charge_state.get("chargeRate"),
            merged_charge_state.get("batteryLevel"),
        )

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
            @callback
            def _send_abrp_update():
                """Send vehicle telemetry to ABRP when data updates."""
                if vehicle_coord.data:
                    hass.async_create_task(
                        abrp_client.async_send_telemetry(vehicle_coord.data)
                    )

            vehicle_coord.async_add_listener(_send_abrp_update)
            _LOGGER.debug("ABRP update listener added to vehicle coordinator")

        # 2c) Set up auto-odometer update if entity is configured
        odometer_entity = entry.options.get(CONF_ODOMETER_ENTITY) or ""
        if odometer_entity:
            _LOGGER.info("Auto-odometer update enabled with entity: %s", odometer_entity)
            # Track previous charging state to detect charge end
            prev_charging_state = {"is_charging": None}

            @callback
            def _check_charging_ended():
                """Check if charging just ended and update odometer."""
                if not vehicle_coord.data:
                    return

                charge_state = vehicle_coord.data.get("chargeState", {})
                current_charging = charge_state.get("isCharging", False)
                was_charging = prev_charging_state["is_charging"]

                # Update previous state
                prev_charging_state["is_charging"] = current_charging

                # Detect transition from charging to not charging
                if was_charging is True and current_charging is False:
                    _LOGGER.info("Charging ended - updating odometer from %s", odometer_entity)

                    async def _do_odometer_update():
                        # Read odometer value from entity
                        state = hass.states.get(odometer_entity)
                        if state is None:
                            _LOGGER.warning("Odometer entity %s not found", odometer_entity)
                            return

                        try:
                            odometer_km = float(state.state)
                        except (ValueError, TypeError):
                            _LOGGER.warning("Invalid odometer value from %s: %s", odometer_entity, state.state)
                            return

                        # Wait a bit for the charging session to be finalized in backend
                        await asyncio.sleep(30)

                        # Call API to update odometer
                        result = await client.async_update_odometer(odometer_km)
                        if result:
                            _LOGGER.info("Auto-updated odometer to %s km after charge ended", odometer_km)
                        else:
                            _LOGGER.warning("Failed to auto-update odometer after charge ended")

                    hass.async_create_task(_do_odometer_update())

            vehicle_coord.async_add_listener(_check_charging_ended)
            _LOGGER.debug("Auto-odometer update listener added to vehicle coordinator")

        # 2d) Set up electricity rate push if entity is configured
        elec_rate_entity = entry.options.get(CONF_ELECTRICITY_RATE_ENTITY) or ""
        elec_rate_currency = (entry.options.get(CONF_ELECTRICITY_RATE_CURRENCY) or "").strip().upper()
        if not elec_rate_currency or len(elec_rate_currency) != 3:
            elec_rate_currency = (hass.config.currency or "").strip().upper()
        if elec_rate_entity and elec_rate_currency and len(elec_rate_currency) == 3:
            _LOGGER.info(
                "Electricity rate push enabled: entity=%s, currency=%s",
                elec_rate_entity, elec_rate_currency,
            )
            # Track the last successfully pushed value to avoid duplicates
            last_pushed = {"rate": None}

            async def _push_rate(rate_value: float):
                """Push the electricity rate to EVConduit."""
                if rate_value == last_pushed["rate"]:
                    _LOGGER.debug("Electricity rate unchanged (%.4f), skipping push", rate_value)
                    return
                result = await client.async_push_electricity_rate(rate_value, elec_rate_currency)
                if result:
                    last_pushed["rate"] = rate_value
                    _LOGGER.info("Pushed electricity rate: %.4f %s", rate_value, elec_rate_currency)

            async def _read_and_push_rate():
                """Read rate from entity and push it."""
                state = hass.states.get(elec_rate_entity)
                if state is None or state.state in ("unknown", "unavailable"):
                    return
                try:
                    rate_value = float(state.state)
                    if rate_value >= 0:
                        await _push_rate(rate_value)
                except (ValueError, TypeError):
                    _LOGGER.debug("Invalid electricity rate value: %s", state.state)

            # Push on state change
            async def _on_rate_change(event):
                """Handle state change of the electricity rate entity."""
                new_state = event.data.get("new_state")
                if new_state is None or new_state.state in ("unknown", "unavailable"):
                    return
                try:
                    rate_value = float(new_state.state)
                    if rate_value >= 0:
                        await _push_rate(rate_value)
                except (ValueError, TypeError):
                    _LOGGER.debug("Invalid electricity rate value on change: %s", new_state.state)

            unsub_rate_listener = async_track_state_change_event(
                hass, [elec_rate_entity], _on_rate_change
            )
            hass.data[DOMAIN][f"{entry.entry_id}_rate_unsub"] = unsub_rate_listener

            # Periodic push every 5 minutes as backup
            async def _periodic_rate_push(_now):
                """Periodically push electricity rate as a backup."""
                await _read_and_push_rate()

            unsub_rate_timer = async_track_time_interval(
                hass, _periodic_rate_push, timedelta(minutes=5)
            )
            hass.data[DOMAIN][f"{entry.entry_id}_rate_timer_unsub"] = unsub_rate_timer

            # Push current value immediately at startup
            hass.async_create_task(_read_and_push_rate())
            _LOGGER.debug("Electricity rate push listeners set up")
        elif elec_rate_entity:
            _LOGGER.warning(
                "Electricity rate entity configured (%s) but currency could not be determined (%s). "
                "Set a 3-letter currency code in options, or configure your HA currency in Settings → General.",
                elec_rate_entity, elec_rate_currency,
            )

        # 2e) Set up charging history sync if enabled
        charging_history_enabled = entry.options.get(CONF_CHARGING_HISTORY, False)
        _LOGGER.warning(
            "---- [EVConduit] Charging history option: %s (all options: %s)",
            charging_history_enabled, dict(entry.options),
        )
        if charging_history_enabled:
            _LOGGER.warning("---- [EVConduit] Charging history sync enabled for entry %s", entry.entry_id)
            store = Store(hass, 1, f"{DOMAIN}.charging_sessions.{entry.entry_id}")
            store_data = await store.async_load() or {"last_sync": None, "sessions": []}
            # Safety: if last_sync is set but no sessions, reset to force full sync
            if store_data.get("last_sync") and not store_data.get("sessions"):
                _LOGGER.warning("---- [EVConduit] Store has last_sync but no sessions, resetting for full sync")
                store_data["last_sync"] = None
            # Mutable state for sync
            ch_state = {
                "store": store,
                "data": store_data,
                "last_sync_time": 0.0,  # monotonic timestamp of last API call
            }
            hass.data[DOMAIN][f"{entry.entry_id}_ch_store"] = ch_state

            async def _sync_charging_history(force: bool = False):
                """Incremental sync of charging sessions from backend."""
                _LOGGER.warning("---- [EVConduit] _sync_charging_history called (force=%s)", force)
                try:
                    now_mono = time.monotonic()
                    if not force and (now_mono - ch_state["last_sync_time"]) < CHARGING_HISTORY_SYNC_INTERVAL:
                        _LOGGER.warning("---- [EVConduit] Sync throttled, skipping")
                        return

                    last_sync = ch_state["data"].get("last_sync")
                    existing_ids = {s["session_id"] for s in ch_state["data"]["sessions"]}
                    all_new = []

                    # Paginate through all new sessions
                    since = last_sync
                    _LOGGER.warning("---- [EVConduit] Fetching sessions since=%s", since)
                    while True:
                        result = await client.async_get_charging_sessions(since=since, limit=50)
                        _LOGGER.warning("---- [EVConduit] API result: %s", result is not None)
                        if not result or not result.get("sessions"):
                            _LOGGER.warning("---- [EVConduit] No sessions in result, breaking")
                            break
                        batch = result["sessions"]
                        _LOGGER.warning("---- [EVConduit] Got %d sessions in batch", len(batch))
                        for s in batch:
                            if s["session_id"] not in existing_ids:
                                all_new.append(s)
                                existing_ids.add(s["session_id"])
                        if not result.get("has_more"):
                            break
                        # Use the last session's start_time as the next `since`
                        since = batch[-1]["start_time"]

                    if all_new:
                        ch_state["data"]["sessions"].extend(all_new)
                        _LOGGER.warning("---- [EVConduit] Charging history: synced %d new sessions", len(all_new))
                    else:
                        _LOGGER.warning("---- [EVConduit] No new sessions to sync")

                    # Update last_sync to the latest session's created_at timestamp
                    # (not datetime.now(), because sessions are created when charging
                    # ends and their start_time can be hours before created_at)
                    if ch_state["data"]["sessions"]:
                        latest_created = max(
                            s.get("created_at", s.get("start_time", ""))
                            for s in ch_state["data"]["sessions"]
                        )
                        ch_state["data"]["last_sync"] = latest_created or datetime.now(timezone.utc).isoformat()
                    else:
                        ch_state["data"]["last_sync"] = None
                        _LOGGER.warning("---- [EVConduit] No sessions stored, keeping last_sync=None for next attempt")
                    ch_state["last_sync_time"] = now_mono
                    await store.async_save(ch_state["data"])

                    # Notify charging history sensors
                    ch_coord = hass.data[DOMAIN].get(f"{entry.entry_id}_ch_coordinator")
                    if ch_coord:
                        ch_coord.async_set_updated_data(ch_state["data"])
                    _LOGGER.warning("---- [EVConduit] Sync complete, %d total sessions stored", len(ch_state["data"]["sessions"]))
                except Exception as exc:
                    _LOGGER.warning("---- [EVConduit] Sync FAILED: %s", exc, exc_info=True)

            # Create a lightweight coordinator for charging history sensors
            async def _ch_update():
                return ch_state["data"]

            ch_coordinator = DataUpdateCoordinator(
                hass, _LOGGER,
                name=f"{DOMAIN} charging history",
                update_method=_ch_update,
                update_interval=None,  # Manual updates only
            )
            # Do a first refresh so CoordinatorEntity considers the data valid
            await ch_coordinator.async_config_entry_first_refresh()
            hass.data[DOMAIN][f"{entry.entry_id}_ch_coordinator"] = ch_coordinator

            # Sync on vehicle coordinator updates (throttled to 15 min)
            @callback
            def _on_vehicle_update():
                hass.async_create_task(_sync_charging_history())

            vehicle_coord.async_add_listener(_on_vehicle_update)

            # Store the sync function for the service
            hass.data[DOMAIN][f"{entry.entry_id}_ch_sync"] = _sync_charging_history

            # Initial sync — runs in background, updates coordinator when done
            async def _initial_sync():
                try:
                    await _sync_charging_history(force=True)
                except Exception:
                    _LOGGER.exception("Error during initial charging history sync")

            hass.async_create_task(_initial_sync())

        # 3) Register global services (once for the domain, dispatched by vehicle_id)
        if not hass.services.has_service(DOMAIN, "set_charging"):
            schema = vol.Schema({
                vol.Required("action"): vol.In(["START", "STOP"]),
                vol.Optional("vehicle_id"): str,
            })

            async def _handle_charging(call):
                action = call.data["action"]
                target_vehicle = call.data.get("vehicle_id")
                _LOGGER.debug("Service set_charging called with action=%s vehicle_id=%s", action, target_vehicle)

                # Find matching client(s)
                domain_data = hass.data.get(DOMAIN, {})
                clients_used = 0
                for e in hass.config_entries.async_entries(DOMAIN):
                    if target_vehicle and e.data.get(CONF_VEHICLE_ID) != target_vehicle:
                        continue
                    c = domain_data.get(f"{e.entry_id}_client")
                    if not c:
                        continue
                    try:
                        result = await c.async_set_charging(action)
                        if result:
                            _LOGGER.info("Charging %s executed for vehicle %s", action, e.data.get(CONF_VEHICLE_ID))
                        else:
                            _LOGGER.error("Charging %s failed for vehicle %s", action, e.data.get(CONF_VEHICLE_ID))
                    except Exception:
                        _LOGGER.exception("Error in set_charging service for vehicle %s", e.data.get(CONF_VEHICLE_ID))
                    clients_used += 1
                    if target_vehicle:
                        break

                if clients_used == 0:
                    _LOGGER.error("No matching vehicle found for set_charging (vehicle_id=%s)", target_vehicle)

            hass.services.async_register(DOMAIN, "set_charging", _handle_charging, schema=schema)
            _LOGGER.debug("Service set_charging registered (global)")

        if not hass.services.has_service(DOMAIN, "update_odometer"):
            odometer_schema = vol.Schema({
                vol.Optional("odometer_entity"): str,
                vol.Optional("odometer_km"): vol.Coerce(float),
                vol.Optional("vehicle_id"): str,
            })

            async def _handle_odometer(call):
                odo_entity = call.data.get("odometer_entity")
                odometer_km = call.data.get("odometer_km")
                target_vehicle = call.data.get("vehicle_id")

                if odo_entity:
                    state = hass.states.get(odo_entity)
                    if state is None:
                        _LOGGER.error("Entity %s not found", odo_entity)
                        return
                    try:
                        odometer_km = float(state.state)
                    except (ValueError, TypeError):
                        _LOGGER.error("Entity %s has invalid state: %s", odo_entity, state.state)
                        return

                if odometer_km is None:
                    _LOGGER.error("No odometer value provided (use odometer_entity or odometer_km)")
                    return

                domain_data = hass.data.get(DOMAIN, {})
                for e in hass.config_entries.async_entries(DOMAIN):
                    if target_vehicle and e.data.get(CONF_VEHICLE_ID) != target_vehicle:
                        continue
                    c = domain_data.get(f"{e.entry_id}_client")
                    if not c:
                        continue
                    try:
                        result = await c.async_update_odometer(odometer_km)
                        if result:
                            _LOGGER.info("Odometer updated to %s km for vehicle %s", odometer_km, e.data.get(CONF_VEHICLE_ID))
                        else:
                            _LOGGER.warning("Odometer update failed for vehicle %s", e.data.get(CONF_VEHICLE_ID))
                    except Exception:
                        _LOGGER.exception("Error in update_odometer service")
                    if target_vehicle:
                        break

            hass.services.async_register(DOMAIN, "update_odometer", _handle_odometer, schema=odometer_schema)
            _LOGGER.debug("Service update_odometer registered (global)")

        if not hass.services.has_service(DOMAIN, "send_abrp_telemetry"):
            async def _handle_send_abrp(call):
                """Force send current vehicle telemetry to ABRP."""
                target_vehicle = call.data.get("vehicle_id") if call.data else None
                domain_data = hass.data.get(DOMAIN, {})
                for e in hass.config_entries.async_entries(DOMAIN):
                    if target_vehicle and e.data.get(CONF_VEHICLE_ID) != target_vehicle:
                        continue
                    abrp = domain_data.get(f"{e.entry_id}_abrp")
                    if not abrp:
                        continue
                    vcoord = domain_data.get(f"{e.entry_id}_vehicle")
                    if not vcoord or not vcoord.data:
                        _LOGGER.warning("No vehicle data for ABRP telemetry (vehicle %s)", e.data.get(CONF_VEHICLE_ID))
                        continue
                    try:
                        await abrp.async_send_telemetry(vcoord.data)
                        _LOGGER.info("ABRP telemetry sent for vehicle %s", e.data.get(CONF_VEHICLE_ID))
                    except Exception:
                        _LOGGER.exception("Error sending ABRP telemetry for vehicle %s", e.data.get(CONF_VEHICLE_ID))
                    if target_vehicle:
                        break

            abrp_schema = vol.Schema({vol.Optional("vehicle_id"): str})
            hass.services.async_register(DOMAIN, "send_abrp_telemetry", _handle_send_abrp, schema=abrp_schema)
            _LOGGER.debug("Service send_abrp_telemetry registered (global)")

        if not hass.services.has_service(DOMAIN, "sync_charging_history"):
            async def _handle_sync_charging_history(call):
                """Trigger an immediate incremental charging history sync."""
                target_vehicle = call.data.get("vehicle_id") if call.data else None
                domain_data = hass.data.get(DOMAIN, {})
                for e in hass.config_entries.async_entries(DOMAIN):
                    if target_vehicle and e.data.get(CONF_VEHICLE_ID) != target_vehicle:
                        continue
                    sync_fn = domain_data.get(f"{e.entry_id}_ch_sync")
                    if not sync_fn:
                        _LOGGER.debug("No charging history sync configured for entry %s", e.entry_id)
                        continue
                    try:
                        await sync_fn(force=True)
                        _LOGGER.info("Charging history sync triggered for vehicle %s", e.data.get(CONF_VEHICLE_ID))
                    except Exception:
                        _LOGGER.exception("Error in sync_charging_history for vehicle %s", e.data.get(CONF_VEHICLE_ID))
                    if target_vehicle:
                        break

            sync_schema = vol.Schema({vol.Optional("vehicle_id"): str})
            hass.services.async_register(DOMAIN, "sync_charging_history", _handle_sync_charging_history, schema=sync_schema)
            _LOGGER.debug("Service sync_charging_history registered (global)")

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
            registered = await client.async_register_webhook(webhook_id, external_url, vehicle_id)
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

    # Only remove global services if this is the last entry being unloaded
    remaining = sum(
        1 for e in hass.config_entries.async_entries(DOMAIN)
        if e.entry_id != entry.entry_id
    )
    if remaining == 0:
        for svc in ("set_charging", "update_odometer", "send_abrp_telemetry", "sync_charging_history"):
            if hass.services.has_service(DOMAIN, svc):
                hass.services.async_remove(DOMAIN, svc)
        _LOGGER.debug("All services removed (last entry unloaded)")

    async_unregister(hass, entry.entry_id)
    _LOGGER.debug("Webhook unregistered for entry %s", entry.entry_id)

    # Note: We intentionally do NOT unregister the webhook from the EVConduit backend
    # on unload/reboot. async_setup_entry always re-registers with the current URL,
    # so unregistering just creates a window where pushes fail. If the user truly
    # removes the integration, they can clear webhook settings from the profile page.

    # Clean up electricity rate listeners
    domain_data = hass.data.get(DOMAIN, {})
    rate_unsub = domain_data.pop(f"{entry.entry_id}_rate_unsub", None)
    if rate_unsub:
        rate_unsub()
    rate_timer_unsub = domain_data.pop(f"{entry.entry_id}_rate_timer_unsub", None)
    if rate_timer_unsub:
        rate_timer_unsub()

    domain_data.pop(entry.entry_id, None)
    domain_data.pop(f"{entry.entry_id}_vehicle", None)
    domain_data.pop(f"{entry.entry_id}_abrp", None)
    domain_data.pop(f"{entry.entry_id}_client", None)
    domain_data.pop(f"{entry.entry_id}_ch_store", None)
    domain_data.pop(f"{entry.entry_id}_ch_coordinator", None)
    domain_data.pop(f"{entry.entry_id}_ch_sync", None)
    return unload_ok

# Lägg till denna!
async def async_reload_entry(hass, entry):
    """Reload EVConduit config entry when options are updated."""
    _LOGGER.info("---- [EVConduit] async_reload_entry called for %s ----", entry.entry_id)
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
    _LOGGER.info("---- [EVConduit] async_reload_entry finished for %s ----", entry.entry_id)
