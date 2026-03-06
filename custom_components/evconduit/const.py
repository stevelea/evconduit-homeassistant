# custom_components/evconduit/const.py

DOMAIN           = "evconduit"
CONF_API_KEY     = "api_key"
CONF_ENVIRONMENT = "environment"
CONF_VEHICLE_ID  = "vehicle_id"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_ABRP_TOKEN = "abrp_token"
CONF_ODOMETER_ENTITY = "odometer_entity"
CONF_ELECTRICITY_RATE_ENTITY = "electricity_rate_entity"
CONF_ELECTRICITY_RATE_CURRENCY = "electricity_rate_currency"
CONF_CHARGING_HISTORY = "charging_history"
DEFAULT_UPDATE_INTERVAL = 4

# Minimum seconds between charging history syncs (15 minutes)
CHARGING_HISTORY_SYNC_INTERVAL = 900

ABRP_API_URL = "https://api.iternio.com/1/tlm/send"

WEBHOOK_ID = f"{DOMAIN}_push_webhook"

ENVIRONMENTS = {
    "prod":    "https://backend.evconduit.com",
    "sandbox": "https://backend.evconduit.com"  
}
# "sandbox2": "http://161.97.70.223:8000"

ICONS = {
    "tier": "mdi:star",
    "email": "mdi:email",
    "name": "mdi:account",
    "role": "mdi:shield-account",
    "sms_credits": "mdi:message-text",
    "webhookId": "mdi:account",
    "chargeState.batteryLevel": "mdi:battery",
    "chargeState.range": "mdi:map-marker-distance",
    "chargeState.isCharging": "mdi:flash",
    "chargeState.isPluggedIn": "mdi:power-plug",
    "chargingState": "mdi:power-socket",
    "vehicleName": "mdi:car",
    "lastSeen": "mdi:clock-outline",
    "lastSeenLocal": "mdi:clock",
    "isReachable": "mdi:lan-connect",
    "chargeState.batteryCapacity": "mdi:battery-charging-100",
    "chargeState.chargeLimit": "mdi:battery-charging-80",
    "chargeState.powerDeliveryState": "mdi:power-plug-outline",
    "chargeState.chargeRate": "mdi:ev-station",
    "chargeState.chargeTimeRemaining":"mdi:timer-sand",
    "information.displayName": "mdi:car-info",
    "information.vin": "mdi:barcode",
    "information.brand": "mdi:car-emergency",
    "information.model": "mdi:car-models",
    "information.year": "mdi:calendar",
    "location.latitude": "mdi:map-marker",
    "location.longitude": "mdi:map-marker",
    "odometer.distance": "mdi:counter",
    "vendor": "mdi:factory",
    "smartChargingPolicy.isEnabled": "mdi:flash-auto",
    "smartChargingPolicy.minimumChargeLimit": "mdi:battery-10",
    "abrp_extra.soh": "mdi:battery-heart-variant",
    "abrp_extra.voltage": "mdi:flash-triangle",
    "abrp_extra.current": "mdi:current-dc",
    "abrp_extra.batt_temp": "mdi:thermometer",
    "abrp_extra.ext_temp": "mdi:thermometer-lines",
    "abrp_extra.cabin_temp": "mdi:car-seat-heater",
    "abrp_extra.hvac_power": "mdi:air-conditioner",
    "abrp_extra.speed": "mdi:speedometer",
    "abrp_extra.elevation": "mdi:elevation-rise",
    "abrp_extra.is_parked": "mdi:car-brake-parking",
    "abrp_extra.odometer": "mdi:counter",
    "abrp_extra.is_dcfc": "mdi:ev-plug-ccs2",
    "abrp_extra.tire_pressure_fl": "mdi:car-tire-alert",
    "abrp_extra.tire_pressure_fr": "mdi:car-tire-alert",
    "abrp_extra.tire_pressure_rl": "mdi:car-tire-alert",
    "abrp_extra.tire_pressure_rr": "mdi:car-tire-alert",
    # Charging history sensors
    "last_charge_energy": "mdi:lightning-bolt",
    "last_charge_cost": "mdi:currency-usd",
    "last_charge_location": "mdi:map-marker",
    "last_charge_date": "mdi:calendar-clock",
    "last_charge_duration": "mdi:timer-outline",
    "monthly_charge_energy": "mdi:lightning-bolt",
    "monthly_charge_cost": "mdi:currency-usd",
    "monthly_charge_count": "mdi:counter",
}

USER_FIELDS = {
    "tier": ("Tier", None),
    "email": ("Email", None),
    "name": ("Name", None),
    "role": ("Role", None),
    "sms_credits": ("SMS Credits", "count"),
}

WEBHOOK_FIELDS = {
    "webhookId": ("Webhook ID", None),
}

VEHICLE_FIELDS = {
    "chargingState": ("Charging State", None),
    "vehicleName": ("Vehicle Name", None),
    "lastSeen": ("Last Seen", None),
    "isReachable": ("Is Reachable", None),
    "chargeState.batteryLevel": ("Battery Level", "%"),
    "chargeState.batteryCapacity": ("Battery Capacity", "kWh"),
    "chargeState.chargeLimit": ("Charge Limit", "%"),
    "chargeState.powerDeliveryState": ("Power Delivery State", None),
    "chargeState.chargeRate": ("Charge Rate", "kW"),
    "chargeState.chargeTimeRemaining":("Charge Time Remaining", "min"),
    "chargeState.isPluggedIn": ("Is Plugged In", None),
    "chargeState.isCharging": ("Is Charging", None),
    "chargeState.range": ("Range", "km"),
    "information.displayName": ("Display Name", None),
    "information.vin": ("VIN", None),
    "information.brand": ("Brand", None),
    "information.model": ("Model", None),
    "information.year": ("Year", None),
    "location.latitude": ("Latitude", "°"),
    "location.longitude": ("Longitude", "°"),
    "odometer.distance": ("Odometer Distance", "km"),
    "vendor": ("Vendor", None),
    "smartChargingPolicy.isEnabled": ("Smart Charging Enabled", None),
    "smartChargingPolicy.minimumChargeLimit": ("Min Charge Limit", "%"),
    "abrp_extra.soh": ("State of Health", "%"),
    "abrp_extra.voltage": ("Battery Voltage", "V"),
    "abrp_extra.current": ("Battery Current", "A"),
    "abrp_extra.batt_temp": ("Battery Temperature", "°C"),
    "abrp_extra.ext_temp": ("Ambient Temperature", "°C"),
    "abrp_extra.cabin_temp": ("Cabin Temperature", "°C"),
    "abrp_extra.hvac_power": ("HVAC Power", "kW"),
    "abrp_extra.speed": ("Speed", "km/h"),
    "abrp_extra.elevation": ("Elevation", "m"),
    "abrp_extra.is_parked": ("Is Parked", None),
    "abrp_extra.odometer": ("Odometer (ABRP)", "km"),
    "abrp_extra.is_dcfc": ("DC Fast Charging", None),
    "abrp_extra.tire_pressure_fl": ("Tire Pressure FL", "bar"),
    "abrp_extra.tire_pressure_fr": ("Tire Pressure FR", "bar"),
    "abrp_extra.tire_pressure_rl": ("Tire Pressure RL", "bar"),
    "abrp_extra.tire_pressure_rr": ("Tire Pressure RR", "bar"),
}

CHARGING_HISTORY_LAST_SESSION_FIELDS = {
    "last_charge_energy": ("Last Charge Energy", "kWh"),
    "last_charge_cost": ("Last Charge Cost", None),
    "last_charge_location": ("Last Charge Location", None),
    "last_charge_date": ("Last Charge Date", None),
    "last_charge_duration": ("Last Charge Duration", "min"),
}

CHARGING_HISTORY_MONTHLY_FIELDS = {
    "monthly_charge_energy": ("Monthly Charge Energy", "kWh"),
    "monthly_charge_cost": ("Monthly Charge Cost", None),
    "monthly_charge_count": ("Monthly Charge Count", "sessions"),
}
