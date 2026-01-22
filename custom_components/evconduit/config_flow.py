from homeassistant import config_entries
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig
import voluptuous as vol
import logging
from .const import DOMAIN, CONF_API_KEY, CONF_VEHICLE_ID, CONF_UPDATE_INTERVAL, CONF_ENVIRONMENT, CONF_ABRP_TOKEN, CONF_ODOMETER_ENTITY, ENVIRONMENTS

from .api import EVConduitClient

DEFAULT_UPDATE_INTERVAL = 6
_LOGGER = logging.getLogger(__name__)

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for EVConduit."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY]
            environment = user_input[CONF_ENVIRONMENT]
            base_url = ENVIRONMENTS[environment]
            _LOGGER.debug(f"[ConfigFlow] User entered API key: {api_key}, environment: {environment}")

            # Validera API-key mot backend!
            try:
                client = EVConduitClient(self.hass, api_key, base_url, "dummy")
                _LOGGER.debug("[ConfigFlow] Created EVConduitClient for API key validation")
                userinfo = await client.async_get_userinfo()
                _LOGGER.debug(f"[ConfigFlow] Result from async_get_userinfo: {userinfo}")

                if not userinfo:
                    _LOGGER.warning("[ConfigFlow] API key validation failed: No userinfo returned")
                    errors["api_key"] = "invalid_api_key"
                else:
                    _LOGGER.info("[ConfigFlow] API key validated successfully, proceeding to vehicle_id step")
                    self.context["api_key"] = api_key
                    self.context["environment"] = environment
                    self.context["abrp_token"] = user_input.get(CONF_ABRP_TOKEN, "")
                    return await self.async_step_vehicle()
            except Exception as e:
                _LOGGER.exception(f"[ConfigFlow] Exception during API key validation: {e}")
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_API_KEY): str,
                vol.Required(CONF_ENVIRONMENT, default="prod"): vol.In(["prod", "sandbox"]),
                vol.Optional(CONF_ABRP_TOKEN): str,
            }),
            errors=errors
        )

    async def async_step_vehicle(self, user_input=None):
        errors = {}
        api_key = self.context["api_key"]
        environment = self.context["environment"]
        base_url = ENVIRONMENTS[environment]
        client = EVConduitClient(self.hass, api_key, base_url, "dummy")
        vehicles = await client.async_get_vehicles()
        # Bygg lista över fordon: label → id
        choices = {}
        for v in vehicles:
            id = v.get("id")  # CORRECT
            if not id:
                _LOGGER.warning(f"[ConfigFlow] Vehicle without ID found: {v}")
                continue

# Build name from information
            info = v.get("information", {})
            name = info.get("displayName")
            if not name:
                brand = info.get("brand", "Unknown")
                model = info.get("model", "")
                name = f"{brand} {model}".strip()
            
            if not name:
                name = "Unknown Vehicle"

            label = id
            choices[label] = f"{name}"
            #choices[label] = f"{name} ({vin})"

        _LOGGER.warning(f"[ConfigFlow] Available vehicles: {choices}")

        if not choices:
            errors["base"] = "no_vehicles"
        
        if user_input is not None:
            vehicle_id = user_input[CONF_VEHICLE_ID]
            entry_data = {
                CONF_API_KEY: api_key,
                CONF_ENVIRONMENT: environment,
                CONF_VEHICLE_ID: vehicle_id,
            }
            # Include ABRP token if provided
            abrp_token = self.context.get("abrp_token", "")
            if abrp_token:
                entry_data[CONF_ABRP_TOKEN] = abrp_token
            _LOGGER.info("[ConfigFlow] Creating config entry with API key, environment and vehicle_id")
            return self.async_create_entry(title="EVConduit", data=entry_data)
        
        return self.async_show_form(
            step_id="vehicle",
            data_schema=vol.Schema({
                vol.Required(CONF_VEHICLE_ID): vol.In(choices)
            }),
            errors=errors
        )


    async def async_step_reconfigure(self, user_input=None):
        entry = self._async_current_entries()[0] if self._async_current_entries() else None
        data = entry.data if entry else {}

        if user_input is not None and entry:
            self.hass.config_entries.async_update_entry(entry, data=user_input)
            _LOGGER.info("Config entry updated via reconfigure.")
            return self.async_abort(reason="reconfigured")

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({
                vol.Required(CONF_API_KEY, default=data.get(CONF_API_KEY, "")): str,
                vol.Required(CONF_ENVIRONMENT, default=data.get(CONF_ENVIRONMENT, "prod")): vol.In(["prod", "sandbox"]),
                vol.Required(CONF_VEHICLE_ID, default=data.get(CONF_VEHICLE_ID, "")): str,
                vol.Optional(CONF_ABRP_TOKEN, default=data.get(CONF_ABRP_TOKEN, "")): str,
            }),
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return EVConduitOptionsFlowHandler()

class EVConduitOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for EVConduit."""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_UPDATE_INTERVAL,
                    default=self.config_entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
                vol.Optional(
                    CONF_ODOMETER_ENTITY,
                    default=self.config_entry.options.get(CONF_ODOMETER_ENTITY, "")
                ): EntitySelector(EntitySelectorConfig(domain="sensor")),
            }),
            description_placeholders={
                "odometer_help": "Select your OBD odometer sensor to auto-update charging sessions"
            },
        )
