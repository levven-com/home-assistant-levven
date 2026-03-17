# Levven Home Assistant Integration

Home Assistant integration for Levven Gateway devices, maintained in the `levven-com/home-assistant-levven` repository (developed by `@jvsinclair`).

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)
[![GitHub release](https://img.shields.io/github/v/release/levven-com/home-assistant-levven)](https://github.com/levven-com/home-assistant-levven/releases)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
[![GitHub stars](https://img.shields.io/github/stars/levven-com/home-assistant-levven)](https://github.com/levven-com/home-assistant-levven/stargazers)

This integration enables Home Assistant to control and monitor Levven devices via the Levven Gateway using MQTT.

## Features

- **Automatic Device Discovery**: Automatically discovers all receivers (controllers) connected to your Levven Gateway
- **Light Control**: Full support for dimmable lights with brightness control (Levven level 0-65535 mapped to HA brightness 0-255)
- **Switch Control**: Support for on/off switches and outlets
- **Real-time Updates**: State changes are reflected immediately via MQTT notifications
- **Switch Events**: Transmitter (switch) presses trigger Home Assistant events for automation
- **Device Management**: Automatic handling of device additions and removals

## Installation

All integration code lives under `custom_components/levven/` in this repository.

Before installing the integration in Home Assistant, it is **strongly recommended** that you:

- Set up your Levven devices (gateway, power controllers, switches) in the Levven Controls app.
- Give each device a meaningful name in the Levven app.

While renaming is supported on the Home Assistant side, doing most of your naming in the Levven app first reduces the chance of name/ID churn that can affect automations and other features in Home Assistant.

### HACS (when published)

Once this repository is added to the public HACS default or as a documented custom repository, installation will look like:

1. Open HACS in Home Assistant.
2. Go to Integrations.
3. Click the three dots menu and select **Custom repositories**.
4. Add this repository URL: `https://github.com/levven-com/home-assistant-levven`.
5. Set the category to **Integration** and add.
6. Search for **Levven** in HACS and install it.
7. Restart Home Assistant.

### Local / Development Testing (current workflow)

Because this repository is not yet a public HACS integration, you can test it locally in two main ways.  
These instructions apply to:

- **Home Assistant OS** (and Supervised): config directory is `/config`.
- **Home Assistant Core** (venv/docker on your own host): config directory is typically `~/.homeassistant` or whatever you configured as the Home Assistant config path.

#### Option 1: Manual install into your Home Assistant config

1. On the machine where Home Assistant is running, locate your configuration directory:
   - Home Assistant OS / Supervised: usually `/config`
   - Home Assistant Core: usually `~/.homeassistant`
2. Ensure the `custom_components` folder exists inside your config directory; create it if it does not.
3. From a terminal on that machine, clone or copy this repository into your config directory (not into another nested repo), so that the path looks like:
   - `<config>/custom_components/levven/manifest.json`
   - `<config>/custom_components/levven/__init__.py`
   - etc.
4. Restart Home Assistant.
5. In Home Assistant, go to **Settings → Devices & Services → Add Integration**.
6. Search for **Levven** and follow the setup instructions.

You can repeat steps 3–4 whenever you update this repository’s code: re-copy/`git pull` into `<config>/custom_components/levven`, then restart Home Assistant.

#### Option 2: HACS custom repository (private testing)

If you have HACS installed and your Home Assistant instance can access this GitHub repository (for example, via a personal access token or once the repo is made public):

1. Make sure HACS is installed and working.
2. In Home Assistant, go to **HACS → Integrations**.
3. Click the three dots menu and choose **Custom repositories**.
4. Add `https://github.com/levven-com/home-assistant-levven` as a repository of type **Integration**.
5. Add the repository and close the dialog.
6. Search for **Levven** under **HACS → Integrations**, install it, and restart Home Assistant.

> **Note**: HACS itself requires that the repository has this `README.md` at the **root** of the repo, plus `hacs.json` in the root, and the integration code under `custom_components/levven/`. The extra `README.md` under `custom_components/levven/` is optional and not used by HACS.

## Configuration

### Prerequisites

- A Levven Gateway connected to your network
- An MQTT broker (Home Assistant's built-in Mosquitto add-on or external broker)
- The gateway must be configured to connect to the same MQTT broker

#### Levven app MQTT configuration (recommended topics)

> A detailed step-by-step guide for configuring the Levven gateway in the app will be published here by Levven. In the meantime, follow the topic settings below and your Levven representative’s integration guide.

When configuring MQTT in the Levven app, you will be asked for **Presence Topic** (birth) and **Last Will Topic** (death).  
The integration expects and subscribes to the following defaults:

- **Presence Topic (birth)**: `levven/v1/notify/gateway/birth`
- **Last Will Topic (death)**: `levven/v1/notify/gateway/death`

The integration treats **any message** on the Presence Topic as “gateway online” and any message on the Last Will Topic as “gateway offline”; the payload is not inspected.

### Setup

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **Levven**.
3. Enter your MQTT broker details:
   - **Host**: MQTT broker hostname or IP address
   - **Port**: MQTT broker port (default: `1883`)
   - **Username**: Optional (but **strongly recommended**) MQTT username
   - **Password**: Optional (but **strongly recommended**) MQTT password
   - **Use TLS**: Enable if your broker uses TLS
4. The integration will automatically discover your gateway and all connected receivers.

During setup you can also choose whether **Transmitters as entities** should be enabled:

- When enabled, each newly discovered Levven switch (transmitter) will be added as an entity.
- You can then attach automations to each button (up and down) using the `levven_switch_pressed` event and the per-transmitter state, giving fine-grained control per physical button. This does not affect any of the configuration within the Levven app so if you need to change swtich to controller mapping its recommended you do that in the Levven app.

### Gateway and device presence (MQTT + mDNS fallback)

Gateway availability is primarily tracked via **MQTT birth/death topics**, with **mDNS** used as a fallback:

- When the Levven Gateway connects to MQTT it publishes to the Presence Topic (`levven/v1/notify/gateway/birth`), which the integration treats as “gateway online”.
- When the gateway disconnects unexpectedly, the broker publishes the configured Last Will Topic (`levven/v1/notify/gateway/death`), which the integration treats as “gateway offline”.
- Additionally, the gateway advertises itself on the local network via mDNS (`_lcap._tcp.local.`); the integration uses this as a secondary signal and fallback if MQTT presence is not configured.

Per-device reachability is tracked via MQTT:

- The integration subscribes to `levven/v1/notify/receiver/status` and uses the `reachable` flag in that payload to mark each receiver as available/unavailable.

## Supported Devices

For an overview of all Levven devices as well as detailed specifications and images of each supported device, refer to the [Levven shop](https://levven.com/shop), such as:

### Receivers (Controllers)

#### Dimmable Receivers (Light Entities)
- **Type 4**: [GPDT15 – 1.5A Dimmer Power Controller](https://levven.com/shop/1-5a-dimmer-power-controller-90)
- **Type 5**: [GPC20 – 20A On/Off Power Controller](https://levven.com/shop/20a-on-off-power-controller-91) (supports dimming in this integration)
- **Type 13**: CP2-4-5 Channel 1 – configurable as dimmer or on/off (part of the [CP2-4D-5 3.5A Dual Output Power Controller](https://levven.com/shop/category/power-controllers-2)); see Configuration below

#### On/Off Receivers (Switch Entities)
- **Type 3**: [GPC10 – 10A On/Off Power Controller](https://levven.com/shop/10a-on-off-power-controller-77)
- **Type 8**: [CP1-4 – 1.5A On/Off/Dimmer Power Controller](https://levven.com/shop/cp14d-111)
- **Type 14**: CP2-4-5 Channel 2 (part of the [CP2-4D-5 3.5A Dual Output Power Controller](https://levven.com/shop/category/power-controllers-2))

### Transmitters (Switches)

Transmitters (switches) can be exposed as entities (if enabled during setup) and fire events when pressed:

- **Type 2** (2019 families), for example:
  - [CSDW – Decorator-Style Switch](https://levven.com/shop/csdw-79)
  - [CSQW – Designer-Style Switch](https://levven.com/shop/csqw-70)
  - [PSW – Portable-Style Switch](https://levven.com/shop/psw-99)
- **Type 10** (2022 models): CSxyyH22 variants (designer-style switches with updated radio hardware)
  - [GPDT15 – 1.5A Dimmer Power Controller](https://levven.com/shop/1-5a-dimmer-power-controller-90)
  - [GPC10 – 10A On/Off Power Controller](https://levven.com/shop/10a-on-off-power-controller-77)
  - [GPC20 – 20A On/Off Power Controller](https://levven.com/shop/20a-on-off-power-controller-91)
  - [CP1-4 – 1.5A On/Off/Dimmer Power Controller](https://levven.com/shop/cp14d-111)
  - [CSDW – Decorator-Style Switch](https://levven.com/shop/csdw-79)
  - [CSQW – Designer-Style Switch](https://levven.com/shop/csqw-70)
  - [PSW – Portable-Style Switch](https://levven.com/shop/psw-99)

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

For correct operation, the gateway should be configured to publish **all** of the above notification topics to your MQTT broker.

### Brightness Mapping

Levven devices use a 0-65535 scale for brightness, while Home Assistant uses 0-255. The integration automatically converts between these scales:
- Levven 0-65535 → HA 0-255
- HA 0-255 → Levven 0-65535

## Limitations

The following features are not yet supported (require gateway firmware updates):

- **Transmitter Discovery**: No automatic discovery of transmitters (switches)
- **Advanced Switch Events**: Hold/dim events are not exposed via MQTT
- **Pairing Mode**: No service to initiate gateway pairing mode
- **Transmitter Info**: No way to get transmitter names or details

## Support

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

## License

This integration is provided as-is for use with Levven devices.

