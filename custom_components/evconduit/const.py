# custom_components/evconduit/const.py

DOMAIN           = "evconduit"
CONF_API_KEY     = "api_key"
CONF_ENVIRONMENT = "environment"
CONF_VEHICLE_ID  = "vehicle_id"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_ABRP_TOKEN = "abrp_token"
DEFAULT_UPDATE_INTERVAL = 6

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
}
