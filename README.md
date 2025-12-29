# EVConduit Home Assistant Integration

[![hacs badge](https://img.shields.io/badge/HACS-Custom-blue.svg?style=flat-square)](https://hacs.xyz/docs/faq/custom_repositories)
![Home Assistant minimum version](https://img.shields.io/badge/HA%20min-2025.5-blue?style=flat-square)
[![MIT License](https://img.shields.io/github/license/stevelea/evconduit-homeassistant?style=flat-square)](LICENSE)
[![GitHub release](https://img.shields.io/github/v/release/stevelea/evconduit-homeassistant?include_prereleases&style=flat-square)](https://github.com/stevelea/evconduit-homeassistant/releases)
[![Issues](https://img.shields.io/github/issues/stevelea/evconduit-homeassistant?style=flat-square)](https://github.com/stevelea/evconduit-homeassistant/issues)

---


**EVConduit** is a Home Assistant integration that makes it easy to connect your electric vehicle to Home Assistant via EVLink.  
The integration supports Xpeng and other vehicles connected through Enode.

---

## Getting Started

1. **Create an account at [evconduit.com](https://evconduit.com)**  
   You must have an EVLink account to use this integration.

2. **Link your vehicle**  
   After logging in to [evconduit.com](https://evconduit.com), follow the instructions to link your vehicle.

3. **Copy your `vehicle_id`**  
   You will find this on your vehicle’s detail page after linking.

4. **Create an API key**  
   Go to your profile at [evconduit.com](https://evconduit.com) and create a new API key.

5. **Copy your API key**  
   This is required to connect Home Assistant to EVConduit.

---

## Installation

**Via HACS:**

- Add this GitHub repository as a “Custom Repository” in HACS (type: “Integration”).
- Search for “EVConduit” in HACS and install the integration.

**Manual installation:**

- Download this repository and place the `evconduit` folder in your `custom_components` directory in your Home Assistant installation.

---

## Configuration

When adding the integration in Home Assistant (Settings > Devices & Services > Add Integration > EVConduit):

- Enter your **API key**
- Enter your **vehicle_id**

You will find both on [evconduit.com](https://evconduit.com) as described above.

---

## Features

- Automatically fetches vehicle data and charging status
- Supports multiple car brands through Enode
- Designed for security, simplicity, and reliability

---

## Support & Questions

- Need help or have questions?  
  Open an [issue here](https://github.com/stevelea/evconduit-homeassistant/issues) or visit [evconduit.com](https://evconduit.com).

---

## Open Source

This integration is open source and under active development.  
Everyone is welcome to contribute!

---
