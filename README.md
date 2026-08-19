# Levven Home Assistant Integration

Home Assistant integration for Levven devices connected through a Levven Q Gateway, maintained in the `levven-com/home-assistant-levven` repository (developed by `@jvsinclair`).

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)
[![GitHub release](https://img.shields.io/github/v/release/levven-com/home-assistant-levven)](https://github.com/levven-com/home-assistant-levven/releases)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
[![GitHub stars](https://img.shields.io/github/stars/levven-com/home-assistant-levven)](https://github.com/levven-com/home-assistant-levven/stargazers)

This integration enables Home Assistant to control and monitor Levven devices via the [Levven Q Gateway](https://levven.com/shop/q-gateway-67) using MQTT.

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Supported Devices](#supported-devices)
- [Usage](#usage)
- [Device Discovery](#device-discovery)
- [Troubleshooting](#troubleshooting)
- [Technical Details](#technical-details)
- [Limitations](#limitations)
- [Support and Contributions](#support-and-contributions)
- [Developer Notes](#developer-notes)

## Features

- **Automatic Device Discovery**: Automatically discovers all receivers (controllers) connected to your Levven Q Gateway
- **Light Control**: Full support for dimmable lights with brightness control
- **Switch Control**: Support for on/off switches and outlets
- **Real-time Updates**: State changes are reflected immediately via MQTT notifications
- **Switch Events**: Transmitter (switch) presses trigger Home Assistant events for automation
- **Device Management**: Automatic handling of device additions and removals

## Prerequisites

Before installing the integration, complete the following:

### 1. Home Assistant

If you do not have a Home Assistant installation, follow the [Home Assistant installation guide](https://www.home-assistant.io/installation/) to set it up.

### 2. Levven Mobile App

Install the Levven Controls app on your mobile device:

[![Download on the App Store](https://img.shields.io/badge/App_Store-0D96F6?style=for-the-badge&logo=app-store&logoColor=white)](https://apps.apple.com/ca/app/levven-controls/id1436898660)
[![Get it on Google Play](https://img.shields.io/badge/Google_Play-414141?style=for-the-badge&logo=google-play&logoColor=white)](https://play.google.com/store/apps/details?id=com.levven.controls)

**Before proceeding**, it is **strongly recommended** that you:

- Set up your Levven devices (gateway, power controllers, switches) in the Levven app
- Give each device a meaningful name in the Levven app

While renaming is supported on the Home Assistant side, doing most of your naming in the Levven app first reduces the chance of name/ID churn that can affect automations.

For additional information, see the [Levven Controls App Support page](https://levven.com/support/levven-controls-mobile-app).

### 3. MQTT Broker

If you have not previously installed the Home Assistant MQTT integration, follow the [Home Assistant MQTT guide](https://www.home-assistant.io/integrations/mqtt/).

#### Mosquitto Broker Configuration

If using the Home Assistant-provided Mosquitto broker, additional configuration is required:

1. Go to **Settings → Devices & Services → MQTT**.

2. Click the three-dot menu and select **Reconfigure**.

   <kbd>
   <img src="https://github.com/levven-com/home-assistant-levven/blob/main/https://github.com/levven-com/home-assistant-levven/blob/main/.github/images/MQTT_reconfig.png" alt="MQTT reconfigure menu" width="600" />
   </kbd>

3. Update your credentials:
   - Change the username from `homeassistant` to your login name
   - Update the password to your Home Assistant password

   These will become your MQTT credentials. Click **Submit**.

   <kbd>
   <img src="https://github.com/levven-com/home-assistant-levven/blob/main/.github/images/MQTT_broker.png" alt="MQTT broker settings" width="500" />
   </kbd>

### 4. HACS

If you have not previously installed HACS, follow the [Start using HACS](https://hacs.xyz/docs/use/) guide.

## Installation

The Levven integration can be installed through HACS as a custom repository:

1. Open HACS in Home Assistant (if not visible, do a hard browser refresh).

   <kbd>
   <img src="https://github.com/levven-com/home-assistant-levven/blob/main/.github/images/HACS_left_panel.png" alt="HACS in left sidebar" width="200" />
   </kbd>

2. Click the three-dot menu and select **Custom repositories**.

   <kbd>
   <img src="https://github.com/levven-com/home-assistant-levven/blob/main/.github/images/custom_repo.png" alt="HACS custom repositories menu" width="600" />
   </kbd>

3. Add the repository:
   - **URL**: `https://github.com/levven-com/home-assistant-levven`
   - **Type**: Integration

4. Search for **Levven** in HACS, select it, and click **Download**.

5. Restart Home Assistant.

## Configuration

### Levven App MQTT Settings

1. In the Levven app, tap the gear icon (upper right) to open settings, then tap **Integrations**.

   <kbd>
   <img src="https://github.com/levven-com/home-assistant-levven/blob/main/.github/images/Levven_settings.png" alt="Levven app settings screen" width="300" />
   </kbd>

2. Set up your integration:
   - If no integrations exist, tap **SETUP YOUR FIRST CONFIGURATION**
   - If one exists, tap it to edit

   <kbd>
   <img src="https://github.com/levven-com/home-assistant-levven/blob/main/.github/images/Levven_MQTT_config.png" alt="Levven MQTT setup screen" width="300" />
   </kbd>
   <kbd>
   <img src="https://github.com/levven-com/home-assistant-levven/blob/main/.github/images/Levven_existing_MQTT_config.png" alt="Levven existing MQTT configuration" width="300" />
   </kbd>

3. Configure the MQTT connection:
   - Select **Levven Universal MQTT** as the broker
   - Enter a name (e.g., "Home Assistant")
   - Enter your **Username** and **Password** (same as configured in MQTT broker)
   - Tap **Advanced Settings** to expand

   <kbd>
   <img src="https://github.com/levven-com/home-assistant-levven/blob/main/.github/images/Levven_new_MQTT_config.png" alt="Levven MQTT configuration form" width="300" />
   </kbd>

4. Configure advanced settings:
   - **URI**: `mqtt://homeassistant:1883` (or your broker's address)
   - **Last Will Topic**: `levven/v1/notify/gateway/death`
   - **Presence Topic**: `levven/v1/notify/gateway/birth`

   Tap **Save**.

   <kbd>
   <img src="https://github.com/levven-com/home-assistant-levven/blob/main/.github/images/Levven_advanced_MQTT_config.png" alt="Levven advanced MQTT settings" width="300" />
   </kbd>

5. Ensure the integration is enabled (toggle should point left).

   <kbd>
   <img src="https://github.com/levven-com/home-assistant-levven/blob/main/.github/images/Levven_HA_MQTT_config.png" alt="Levven integration toggle enabled" width="300" />
   </kbd>

### Home Assistant Integration Setup

1. Go to **Settings → Devices & Services → Add Integration**.

2. Search for **Levven**.

3. Enter your MQTT broker details:
   - **Host**: Broker hostname or IP (use `localhost` for Mosquitto add-on)
   - **Port**: Broker port (default `1883`)
   - **Username**: Same as configured in MQTT broker and Levven app
   - **Password**: Same as configured in MQTT broker and Levven app
   - **Use TLS**: Enable if your broker uses TLS
   - **Transmitters as entities**: Enable to expose physical switches as entities for automations

   <kbd>
   <img src="https://github.com/levven-com/home-assistant-levven/blob/main/.github/images/Levven_HA_config.png" alt="Home Assistant Levven integration setup" width="500" />
   </kbd>

4. Click **Submit**. The integration will automatically discover your gateway and connected receivers.

### Gateway Presence Detection

Gateway availability is tracked via **MQTT birth/death topics**, with **mDNS** as a fallback:

- **Online**: Gateway publishes to `levven/v1/notify/gateway/birth`
- **Offline**: Broker publishes `levven/v1/notify/gateway/death` (Last Will)
- **Fallback**: Gateway advertises via mDNS (`_lcap._tcp.local.`)

Per-device reachability uses the `reachable` flag from `levven/v1/notify/receiver/status`.

## Supported Devices

For an overview of all Levven devices, refer to the [Levven shop](https://levven.com/shop).

### Receivers (Controllers)

#### Dimmable Receivers (Light Entities)
- **Type 4**: [GPDT15 – 1.5A Dimmer Power Controller](https://levven.com/shop/1-5a-dimmer-power-controller-90)
- **Type 5**: [GPC20 – 20A On/Off Power Controller](https://levven.com/shop/20a-on-off-power-controller-91)
- **Type 13**: CP2-4-5 Channel 1 – configurable as dimmer or on/off (part of the [CP2-4D-5 3.5A Dual Output Power Controller](https://levven.com/shop/category/power-controllers-2)); see Configuration below

#### On/Off Receivers (Switch Entities)
- **Type 3**: [GPC10 – 10A On/Off Power Controller](https://levven.com/shop/10a-on-off-power-controller-77)
- **Type 8**: [CP1-4 – 1.5A On/Off/Dimmer Power Controller](https://levven.com/shop/cp14d-111)
- **Type 14**: CP2-4-5 Channel 2 (part of the [CP2-4D-5 3.5A Dual Output Power Controller](https://levven.com/shop/category/power-controllers-2))

### Transmitters (Switches)

Transmitters (switches) can be exposed as entities (if enabled during setup) and fire events when pressed:

- **Type 2** (models made up to 2022), for example:
  - [CSDW – Decorator-Style Switch](https://levven.com/shop/csdw-79)
  - [CSQW – Designer-Style Switch](https://levven.com/shop/csqw-70)
  - [PSW – Portable-Style Switch](https://levven.com/shop/psw-99)
- **Type 10** (models made in 2022 and later): CSxyH22 variants (designer-style switches with updated radio hardware)
  - [CSDWH22 – Decorator-Style Switch](https://levven.com/shop/csdw-79)
  - [CSQWH22 – Designer-Style Switch](https://levven.com/shop/csqw-70)

## Entity Type Configuration

### Configuring CP2-4-5 Channel 1 Entity Type

Device type 13 (CP2-4-5 Channel 1) can be configured as either a dimmer (light) or on/off (switch) in the Levven app. By default, Home Assistant will detect the entity type based on whether the device reports a brightness level. However, you can manually configure the entity type using the `levven.set_entity_type` service:

```yaml
service: levven.set_entity_type
data:
  entity_id: light.levven_device_name  # or switch.levven_device_name
  entity_type: light  # or "switch"
```

After calling this service, you'll need to reload the Levven integration for the change to take effect. The preference is stored in the entity registry and will persist across restarts.

**Note**: The entity type configuration in Home Assistant is independent of the Levven app configuration. Make sure both are set correctly for your use case.

## Usage

### Controlling Lights

Lights can be controlled through Home Assistant's UI or via automations:

```yaml
# Turn on light at 50% brightness
service: light.turn_on
target:
  entity_id: light.levven_light_name
data:
  brightness: 128  # 50% of 255
```

### Controlling Switches

Switches can be toggled on/off:

```yaml
service: switch.turn_on
target:
  entity_id: switch.levven_switch_name
```

### Switch Press Events

When a Levven transmitter (switch) is pressed, it fires a `levven_switch_pressed` event that can be used in automations:

```yaml
automation:
  - alias: "React to Levven Switch Press"
    trigger:
      platform: event
      event_type: levven_switch_pressed
      event_data:
        tuid: "00000001"  # Optional: specific switch
    action:
      - service: light.toggle
        target:
          entity_id: light.example_light
```

Event data includes:
- `tuid`: Transmitter UID
- `is_on`: Current switch state (`true` / `false`)
- `gateway_id`: Gateway ID

## Device Discovery

The integration automatically discovers devices when:
- The integration is first set up
- A new receiver is added to the gateway (via `notify.receiver.new` notification)
- Home Assistant is restarted

Devices are automatically removed when:
- A receiver is deleted from the gateway (via `notify.receiver.delete` notification)

## Troubleshooting

### Devices Not Appearing

1. Check that your MQTT broker is running and accessible.
2. Verify the gateway is connected to the MQTT broker.
3. Check Home Assistant logs for errors.
4. Ensure the gateway has receivers configured.

### State Not Updating

1. Verify MQTT notifications are being received (check MQTT broker logs).
2. Check that the gateway is publishing to the correct topics.
3. Review Home Assistant logs for MQTT subscription errors.

### Connection Issues

1. Verify MQTT broker host and port are correct.
2. Check firewall settings if using a remote broker.
3. Ensure MQTT credentials are correct.
4. For TLS, verify certificates are valid.

## Technical Details

<details>
<summary>Click to expand MQTT topics and technical information</summary>

### MQTT Topics

The integration uses the following MQTT topics (as defined in the gateway's MQTT-RPC bridge):

**Command Topics (Subscribers):**
- `levven/v1/gateway/getinfo` - Get gateway information
- `levven/v1/receivers/list` - List all receiver UIDs
- `levven/v1/receiver/getinfo` - Get receiver information
- `levven/v1/onoff/set` - Set on/off state
- `levven/v1/level/set` - Set brightness level
- `levven/v1/onoff/get` - Get on/off state
- `levven/v1/level/get` - Get brightness level

**Notification Topics (Publishers):**
- `levven/v1/notify/gateway/info` - Gateway info updates (includes `gwid`, name, etc.)
- `levven/v1/notify/level` - Brightness level changes
- `levven/v1/notify/onoff` - On/off state changes
- `levven/v1/notify/receiver/new` - New receiver added
- `levven/v1/notify/receiver/delete` - Receiver removed
- `levven/v1/notify/receiver/info` - Receiver info updates (name/type/level/dimmable)
- `levven/v1/notify/receiver/status` - Receiver availability (`reachable` flag used for HA availability)
- `levven/v1/notify/transmitter/onoff` - Transmitter press events (used for `levven_switch_pressed` HA events)

For full functionality, the gateway should be configured to publish **all** of the above notification topics to your MQTT broker.

### Brightness Mapping

Levven devices use a 0-65535 scale for brightness, while Home Assistant uses 0-255. The integration automatically converts between these scales:
- Levven 0-65535 → HA 0-255
- HA 0-255 → Levven 0-65535

</details>

## Limitations

The following features are not yet supported (require gateway firmware updates):

- **Transmitter Discovery**: No automatic discovery of transmitters (switches)
- **Advanced Switch Events**: Hold/dim events are not exposed via MQTT
- **Pairing Mode**: No service to initiate gateway pairing mode
- **Transmitter Info**: No way to get transmitter names or details

## Support and Contributions

This integration is provided as-is for use with Levven Electronics devices.

Issues and pull requests are welcome, but this repository is maintained on a best-effort basis. Levven does not guarantee response times, support availability, or acceptance of proposed changes. For commercial support, contact Levven through normal support channels.

For issues, feature requests, or questions:

- Open an issue on the GitHub repository: `https://github.com/levven-com/home-assistant-levven/issues`
- Include **logs with debug enabled** and **screenshots** where relevant to help us diagnose problems quickly.

To enable debug logging for this integration, add the following to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.levven: debug
```

Then:

1. Restart Home Assistant.
2. Reproduce the issue (for example, by running the failing flow again).
3. Go to **Settings → System → Logs** and download or copy the relevant entries for `custom_components.levven`.
4. When filing the GitHub issue, include:
   - A short description of what you were doing.
   - The exact error messages and stack traces from the logs (redact any secrets such as hostnames or credentials).
   - Screenshots of the **Levven app configuration**, **Home Assistant integration setup screen**, and any failing entities or automations, if applicable.

You can also use the Home Assistant community forums for general “how do I…” questions, but for bugs we strongly prefer GitHub issues with logs as above.
## Developer Notes

You can also use the Home Assistant community forums for general “how do I…” questions, but for bugs we strongly prefer GitHub issues with logs as above.

## Developer Notes

HACS requires this repository structure:
- `README.md` at the root
- `hacs.json` at the root
- Integration code under `custom_components/levven/`

## License

MIT License. See [LICENSE](LICENSE).
