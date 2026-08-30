# MOVA Viax for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Home Assistant custom integration for **MOVA ViAX** robotic lawn mowers. It
exposes mower control plus the three features ViAX owners usually want first:

- **Camera / map image** — garden map as a Home Assistant camera entity
- **Live map** — mower position and cut path while a session is running
- **Bluetooth** — connection status from the mower

Setup uses your **MOVAhome** (or Dreamehome) account. This project is a
ViAX-focused HACS package of the community Dreame/MOVA mower protocol work.

> Community-developed and not affiliated with MOVA or Dreame. Use with devices
> you own.

## Features

- Start, pause, resume, stop, and dock
- Live map camera with rotation, title, and legend options
- ViAX saved-map fallback for models such as **ViAX 300**
  (`mova.mower.g2420b`) that publish cloud JSON map records instead of a
  streaming vector map
- Bluetooth connection sensor
- Battery, charging, progress, rain protection, and consumables
- Map, zone, edge, and spot selection
- MOVAhome and Dreamehome login, including EU / US / CN / SG / RU

## Supported mowers

Any `mova.mower.*` or `dreame.mower.*` device on the account can be added.
Recognized retail names include:

| Model | Identifier |
| --- | --- |
| MOVA ViAX 300 | `mova.mower.g2420b` |
| MOVA 600 / 600 Kit / 1000 | `mova.mower.g2405a` / `g2405b` / `g2405c` |
| MOVA LiDAX Ultra 800 / 1000 / 2000 | `mova.mower.g2529b` / `g2529c` / `g2529f` |
| Dreame A1 / A1 Pro / A2 | `dreame.mower.p2255` / `g2422` / `g2408` |

Other ViAX and LiDAX variants are discovered automatically from the cloud.
Treat unlisted firmware or region-gated features as experimental.

## Install with HACS

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=pete91-prog&repository=MOVA-Viax&category=integration)

1. Install [HACS](https://hacs.xyz/) if you do not already have it.
2. Click the button above, or in HACS go to **Custom repositories** and add:
   - URL: `https://github.com/pete91-prog/MOVA-Viax`
   - Category: **Integration**
3. Search for **MOVA Viax** and install it.
4. Restart Home Assistant.
5. Go to **Settings → Devices & services → Add integration** and add
   **MOVA Viax**.

### Manual install

1. Copy `custom_components/mova_viax` into your Home Assistant config:
   `<config>/custom_components/mova_viax`
2. Restart Home Assistant.
3. Add **MOVA Viax** from **Settings → Devices & services**.

## Setup

1. Choose **MOVAhome** for ViAX mowers (default).
2. Enter the same email and password used in the official app. Use a password
   with ASCII letters and digits if login is rejected.
3. Select the server country that matches the app (Europe is `eu`).
4. Pick the mower if more than one device is on the account.

Do not use Apple / Google sign-in accounts. Create an email-and-password
MOVAhome login first.

## Works without internet (LAN)

Cloud MQTT is the default path. If you cut the internet, Home Assistant can
still start, pause, and dock the mower **on the same Wi-Fi** using the local
miIO port.

The integration stores the robot's LAN IP and token the next time it talks
to the cloud, so an existing setup keeps working after a later outage. You
can also set them by hand:

1. Open **Settings → Devices & services → MOVA Viax → Configure**.
2. Set **Mower IP address** to the robot's LAN IP.
3. Paste the 32-character **miIO token** if you have one. Leave it blank to
   try the default token.
4. Turn on **Prefer local LAN control** if you want commands to skip the
   cloud whenever the robot answers on the LAN.

Maps and live tracking still need the cloud. The physical control panel on
the mower always works offline.

## Entities

| Entity | What it shows |
| --- | --- |
| `lawn_mower.*` | Start, pause, dock |
| `camera.*_map` | Garden map and live cut path |
| `sensor.*_bluetooth_connection` | Bluetooth connected / not connected |
| Battery, charging, progress, rain, consumables | Status and maintenance |

Map options (rotation, title, legend, padding) are in the integration
**Configure** dialog.

## Credits

Protocol, live-map camera, and Bluetooth handling are based on the MIT-licensed
[antondaubert/dreame-mower](https://github.com/antondaubert/dreame-mower)
integration. ViAX JSON saved-map rendering follows the approach from
[F1nn-T/dreame-ha](https://github.com/F1nn-T/dreame-ha) / madninjaskillz.

## License

MIT. See [LICENSE](LICENSE).
