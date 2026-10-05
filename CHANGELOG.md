# Changelog

All notable changes to this project will be documented in this file. Follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## \[1.15.0] - 2026-10-05

### Added

* A **Push Vehicle State** service, which writes values straight into the
  vehicle's cache. That cache is filled from the car or from a linked data
  source, and until now nothing in Home Assistant could put a number into it —
  so a reading from an OBD dongle, a separate tyre-pressure sensor, or a
  correction for something the car reports wrongly had nowhere to live. Call
  `evconduit.push_vehicle_state` with `fields`, a mapping of dotted cache paths
  to values: `chargeState.batteryLevel: 72`, `location.latitude: -33.8688`,
  `abrp_extra.tire_pressure_fl: 240`.
* The paths are the backend's own cache paths, the same ones the status payload
  uses. An unknown or read-only path fails the whole call and writes nothing,
  so a mapping with one bad key in it stores none of the good ones — the log
  names every path that was sent, because the mistake is in the mapping and
  retrying it unchanged will never succeed.
* `observed_at` is optional and takes an ISO 8601 timestamp, for backfilling a
  reading taken earlier; leave it out to store the values as of now.
* Uses the same per-vehicle dispatch as the other services: with one car
  configured there is nothing to specify, and `vehicle_id` picks one when
  several are. Requires a backend that serves
  `POST /api/ha/vehicle/{vehicle_id}/state`; without it the service is still
  registered and reports the failure in the log.
* `fields` is accepted as JSON text as well as a mapping, and the text form is
  the one to use from an automation. Home Assistant renders a templated value in
  `data:` to a string, so a dict built in a template arrives as its repr — with
  its numbers and booleans no longer numbers and booleans, which the backend
  rejects. End the template with `| tojson` and pass the result.

### Fixed

* **Every service in this integration was missing its description and its
  fields in the Home Assistant UI.** `services.yaml` failed to parse as a whole,
  because the `post_charging_session` latitude and longitude selectors asked for
  `step: 0.000001` and Home Assistant rejects a step below `0.001`. One invalid
  selector took the rest of the file with it. Both now use `step: any`, which is
  what a coordinate wants anyway — the step only controls slider granularity,
  never the value you type.

---

## \[1.14.0] - 2026-09-17

### Added

* **The car can now be added to Home Assistant's Energy Dashboard.** Two new
  sensors, **Total Charge Energy** and **Home Charge Energy**, report cumulative
  kWh with `device_class: energy` and `state_class: total_increasing` — the pair
  of attributes the Energy Dashboard requires before it will list a sensor under
  **Individual Devices**. Add them under **Settings → Dashboards → Energy →
  Individual Devices → Add Device**, and Home Assistant will chart the car's
  charging and price it at whatever rate is configured there.
* They read the backend's `GET /api/ha/charging/energy-total` aggregate rather
  than summing the charging history the integration already holds. That history
  is paged by the API, and a commuter passes the page cap in about a year, so a
  locally summed total would quietly stop growing — and on a `total_increasing`
  sensor an omission is permanent, because Home Assistant only ever adds
  positive deltas.
* Both are registered whenever **Charging History** is enabled, alongside the
  existing last-charge and 30-day sensors.

### Notes

* **`Home Charge Energy` reads 0 on an account that has only ever uploaded a car
  data export.** Home charging is classified from the car's coordinates, and an
  export contains no GPS at all. That is a missing classification rather than
  missing energy — **Total Charge Energy** is complete either way.
* **The endpoint totals the whole account.** The sensors use the per-vehicle
  figure for this entry's vehicle where the backend reports one, a
  single-vehicle account's figure when there is only one car, and report
  *unknown* rather than attributing another car's charging to this one when a
  multi-car account cannot be resolved.
* **A total can go down**, when a charge is corrected downwards or a session is
  deleted. Home Assistant reads a decrease on a `total_increasing` sensor as a
  meter reset and counts on from the new value, which is the honest outcome; the
  alternative hides a correction from the person paying for the electricity. A
  fetch that fails reports *unknown*, never 0, so a network problem is not
  recorded as the meter resetting.

## \[1.13.2] - 2026-09-13

### Changed

* Four more sensors are **disabled by default** for a car connected through
  ABRP: Charge Limit, Power Delivery State, Smart Charging Enabled and Min Charge
  Limit. The ABRP feed carries none of them, so on an ABRP-fed car they could
  only ever read "unknown".
* They are gated on the vehicle's data source rather than switched off outright.
  An Enode-linked car fills all four and keeps its sensors, and a car linked
  through both sources has the values copied onto its ABRP row — so the field's
  presence is checked as well, and only fields that are genuinely absent are
  switched off.
* A car that later moves to a source which can fill them has the sensors this
  integration switched off switched back on again. One you disabled yourself is
  never touched: the registry records who did it, and only our own doing is
  undone.
* The sensor gating above needs a backend that reports `source` in the vehicle
  status response; without it nothing is treated as ABRP-fed and those sensors
  stay exactly as they are, so this is safe to install before the backend is
  updated. The two fixes below need no backend change.

### Fixed

* **Data is no longer pushed back into ABRP when it came from ABRP.** EVConduit
  pulls an ABRP-linked car from ABRP, hands it to Home Assistant, and Home
  Assistant was handing it straight back — so ABRP was told its own last-known
  reading was a current one, and the car's real state of charge never reached
  it. A car asleep overnight could be reported at the same percentage for hours
  while the car itself said something quite different.
* Telemetry sent to ABRP now carries **the time the reading was taken**, not the
  time it was sent. Stamping "now" on a value read hours ago made stale data
  indistinguishable from live data, both to ABRP's route planning and back to us
  through the pull.
* The loop is broken whether or not the backend reports `source`: a vehicle
  whose payload carries `abrp_extra` is one EVConduit has pulled from ABRP, so
  that alone is enough to recognise the data as ABRP's own.

---

## \[1.13.1] - 2026-09-13

### Changed

* Six sensors that no data source has ever supplied are now **disabled by
  default**, so they no longer sit at "unknown" on every dashboard: Cabin
  Temperature, HVAC Power, and the four Tyre Pressure sensors. ABRP documents no
  `hvac_*`, `cabin_temp` or `tire_pressure_*` telemetry at all, and the backend
  stopped collecting them rather than leaving dead lookups in every payload. The
  sensors are still created, so a future source can fill them — enable one from
  the entity's settings if you want to watch for it.
* An install that predates this keeps them enabled, because Home Assistant only
  applies the default the first time a sensor is registered, so each one is
  switched off directly as well — but only while it has still never produced a
  value, leaving any sensor a source does fill untouched. Nothing can tell a
  hand-enabled sensor from a default one, so a never-supplied sensor you switch
  back on is switched off again on the next restart.

---

## \[1.13.0] - 2026-08-27

### Added

* A **Consumption** sensor, in kWh/100 km, showing the consumption your car's
  own range estimate is built on. Every car reports a battery percentage, a
  pack size and a predicted range, and it arrived at that range by assuming a
  consumption — dividing the energy actually in the battery by the range
  offered gives that assumption back.
* This is not measured consumption, and that is what makes it useful: it is
  what the car currently believes about itself, so it drops in the cold, on the
  motorway, or with the car loaded. It is the number to graph against outside
  temperature, or to trigger an alert on when the range looks short before a
  long drive.
* The sensor is unknown rather than wrong below 5% battery or under 10 km of
  range. Battery level arrives as a whole percent, and near empty that rounding
  alone can move the answer by more than a tenth. It is also unknown for
  vehicles whose data source never reports a battery capacity, since there is
  nothing to divide.
* Requires a backend that supplies `chargeState.consumptionKwhPer100Km`. The
  sensor is created either way and simply stays unknown without it.

---

## \[1.12.0] - 2026-08-27

### Added

* Norwegian Bokmål translation (`nb`), contributed by @monsivar in #10.

### Fixed

* No longer triggers Home Assistant's deprecation warning for `TrackerEntity`
  (#11). The class is now imported from `homeassistant.components.device_tracker`
  rather than the deprecated `...device_tracker.config_entry` alias, which is
  scheduled for removal in HA Core 2027.6. Reported by @Swiiney.
* The **charging history** option in the integration's settings had no
  translated label in any language, so it showed as a raw key. Added to
  English, German, Swedish and Norwegian.

---

## \[1.11.0] - 2026-08-27

### Changed

* The model year sensor now reports the year encoded in the VIN rather than the
  year the data source claims. Enode returns the same year for every car of a
  model regardless of build date — it disagreed with the VIN on 94 of 111
  vehicles — whereas VIN position 10 encodes the year directly.
* The year reported by the data source is kept on the sensor as a
  `reported_by_source` attribute, alongside `value_source` (`vin` or `vendor`),
  so nothing is lost and it is always clear which was used.
* The device's model line uses the same year as the sensor.
* Where no year can be read from the VIN, the source's year is used exactly as
  before. Requires a backend that supplies `information.vinModelYear`; without
  it the sensor behaves as it did previously.

---

## \[1.10.0] - 2026-08-27

### Added

* New `image` entity exposing the vehicle's manufacturer artwork, sourced from the
  backend's `information.imageUrl`. Usable directly in picture-entity and
  picture-glance dashboard cards.
* The entity is only created when the linked vehicle actually has artwork — Enode
  is currently the only source that provides it, so ABRP, Tibber and Smartcar
  vehicles get no broken placeholder.

---

## \[1.5.2] - 2026-02-02

### Added

* New `send_abrp_telemetry` service to force send vehicle data to A Better Route Planner on demand

---

## \[1.5.1] - 2026-02-02

### Improved

* Reduced log noise for transient network errors (timeouts, connection issues)
* Network errors now logged as warnings instead of full exception tracebacks
* Affected methods: userinfo, vehicle status, charging, vehicles list, webhook registration, odometer update

---

## \[0.1.0] - 2024-06-27

### First Public/Production Release

#### Major Features

* Initial integration with Home Assistant via custom component `evconduit`.
* Support for vehicle data retrieval (status, location, charge state, odometer, etc.) via EVConduit API.
* Configuration flow for API key, environment (prod/sandbox), and vehicle selection.
* Sensor platform setup for all major vehicle fields (battery, charging, range, etc.).
* Push webhook handler for real-time updates from backend to HA entities.
* Support for charge control (start/stop) via service.
* User info sensors (tier, email, name, role, SMS credits).
* Admin and debugging improvements (extensive logging).

#### Improvements

* Validation of API key during setup.
* Option to select environment (prod/sandbox) during installation and reconfiguration.
* Modular code structure; easy to add new sensors/entities.
* Webhook ID visible as sensor to assist with backend integration.
* Internal error handling and notifications for connection issues, API errors, rate limiting, etc.
* Automatic disabling of non-capable sensors based on capabilities from backend.

#### Fixes

* Fix for stale entity registration and duplicated entities after multiple installs.
* Improved merge logic in webhook payload handling.
* Error handling for missing vehicle data in webhook events.
* Logging of every critical operation for debugging purposes.

#### Developer Experience

* Internal refactoring for future scalability.
* First version of full test/deployment cycle verified with Docker and Home Assistant 2025.5.
* Added support for both manual and automated vehicle updates (polling & push).

---

## \[0.0.1-beta] - 2024-05-31

### Prerelease / Initial Beta

* Initial commit and experimental HA custom component
* Early API polling and sensor registration
* First working push notification via webhook
* Not recommended for production use

---

*Full commit details available in the Git log/history for transparency.*
