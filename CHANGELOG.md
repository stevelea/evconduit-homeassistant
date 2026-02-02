# Changelog

All notable changes to this project will be documented in this file. Follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
