"""Constants for the Levven integration."""

DOMAIN = "levven"

# MQTT Topics (from mqtt_config.c)
TOPIC_GATEWAY_GETINFO = "levven/v1/gateway/getinfo"
TOPIC_RECEIVERS_LIST = "levven/v1/receivers/list"
TOPIC_RECEIVER_GETINFO = "levven/v1/receiver/getinfo"
TOPIC_ONOFF_GET = "levven/v1/onoff/get"
TOPIC_ONOFF_SET = "levven/v1/onoff/set"
TOPIC_LEVEL_GET = "levven/v1/level/get"
TOPIC_LEVEL_SET = "levven/v1/level/set"

# Notification topics
TOPIC_NOTIFY_GATEWAY_INFO = "levven/v1/notify/gateway/info"
TOPIC_NOTIFY_GATEWAY_BIRTH = "levven/v1/notify/gateway/birth"
TOPIC_NOTIFY_GATEWAY_DEATH = "levven/v1/notify/gateway/death"
TOPIC_NOTIFY_LEVEL = "levven/v1/notify/level"
TOPIC_NOTIFY_ONOFF = "levven/v1/notify/onoff"
TOPIC_NOTIFY_RECEIVER_NEW = "levven/v1/notify/receiver/new"
TOPIC_NOTIFY_RECEIVER_DELETE = "levven/v1/notify/receiver/delete"
TOPIC_NOTIFY_RECEIVER_INFO = "levven/v1/notify/receiver/info"
TOPIC_NOTIFY_RECEIVER_STATUS = "levven/v1/notify/receiver/status"
TOPIC_NOTIFY_TRANSMITTER_ONOFF = "levven/v1/notify/transmitter/onoff"

# Response topic pattern
RESPONSE_TOPIC_PREFIX = "ha/levven/response"

# Device Types (from device types table)
DEVICE_TYPE_SWITCH_2019 = 2  # CSxyy, PSyy, GSyy, PDKyy (2019 models)
DEVICE_TYPE_RECEIVER_ONOFF_10A = 3  # GPC10
DEVICE_TYPE_RECEIVER_DIMMER_15A = 4  # GPDT15
DEVICE_TYPE_RECEIVER_ONOFF_20A = 5  # GPC20
DEVICE_TYPE_GATEWAY_2019 = 7  # Levven Q Gateway (2019)
DEVICE_TYPE_RECEIVER_CP1_4 = 8  # CP1-4
DEVICE_TYPE_SWITCH_2022 = 10  # CSxyyH22 (2022 models)
DEVICE_TYPE_RECEIVER_CP2_4_5_CH1 = 13  # CP2-4-5 Channel 1 (dimmer)
DEVICE_TYPE_RECEIVER_CP2_4_5_CH2 = 14  # CP2-4-5 Channel 2 (on/off)
DEVICE_TYPE_GATEWAY_2026 = 20  # Levven Q Gateway (2026)

# Dimmable receiver types
DIMMABLE_RECEIVER_TYPES = {
    DEVICE_TYPE_RECEIVER_DIMMER_15A,
    DEVICE_TYPE_RECEIVER_CP2_4_5_CH1,
}

# On/off only receiver types
ONOFF_RECEIVER_TYPES = {
    DEVICE_TYPE_RECEIVER_ONOFF_10A,
    DEVICE_TYPE_RECEIVER_ONOFF_20A,
    DEVICE_TYPE_RECEIVER_CP1_4,
    DEVICE_TYPE_RECEIVER_CP2_4_5_CH2,
}

# Configurable receiver types (can be dimmer or on/off based on user preference)
CONFIGURABLE_RECEIVER_TYPES = {
    DEVICE_TYPE_RECEIVER_CP2_4_5_CH1,  # Can be configured as dimmer or on/off
}

# Transmitter (switch) types
TRANSMITTER_TYPES = {
    DEVICE_TYPE_SWITCH_2019,
    DEVICE_TYPE_SWITCH_2022,
}

# Gateway types (not entities)
GATEWAY_TYPES = {
    DEVICE_TYPE_GATEWAY_2019,
    DEVICE_TYPE_GATEWAY_2026,
}

# Device type to product model (Levven Device Types table)
DEVICE_TYPE_TO_MODEL: dict[int, str] = {
    DEVICE_TYPE_SWITCH_2019: "CSxyy / PSyy / GSyy / PDKyy",
    DEVICE_TYPE_RECEIVER_ONOFF_10A: "GPC10",
    DEVICE_TYPE_RECEIVER_DIMMER_15A: "GPDT15",
    DEVICE_TYPE_RECEIVER_ONOFF_20A: "GPC20",
    DEVICE_TYPE_GATEWAY_2019: "Levven Q Gateway (2019)",
    DEVICE_TYPE_RECEIVER_CP1_4: "CP1-4",
    DEVICE_TYPE_SWITCH_2022: "CSxyyH22",
    DEVICE_TYPE_RECEIVER_CP2_4_5_CH1: "CP2-4-5 Channel 1",
    DEVICE_TYPE_RECEIVER_CP2_4_5_CH2: "CP2-4-5 Channel 2",
    DEVICE_TYPE_GATEWAY_2026: "Levven Q Gateway (2026)",
}

# Config entry keys
CONF_INCLUDE_TRANSMITTERS = "include_transmitters"

# Entity types
ENTITY_TYPE_LIGHT = "light"
ENTITY_TYPE_SWITCH = "switch"

# Event types
EVENT_SWITCH_PRESSED = "levven_switch_pressed"

# Transmitter tri-state (sensor): idle = nothing pressed, up/down = momentary press
# Future: long_press in payload can map to long_up / long_down
TRANSMITTER_STATE_IDLE = "idle"
TRANSMITTER_STATE_UP = "up"
TRANSMITTER_STATE_DOWN = "down"
TRANSMITTER_STATE_LONG_UP = "long_up"  # reserved for future Levven long-press up
TRANSMITTER_STATE_LONG_DOWN = "long_down"  # reserved for future Levven long-press down
TRANSMITTER_PRESS_RELEASE_DELAY = 2.0  # seconds until state returns to idle after press

# RPC timeout
RPC_TIMEOUT = 10  # seconds

# Level scale (Levven Feb 2026): 0-65535 (16-bit) for all dimmable devices; HA uses 0-255
LEVVEN_LEVEL_MAX = 65535
BRIGHTNESS_SCALE_LEVVEN_TO_HA = 255 / 65535
BRIGHTNESS_SCALE_HA_TO_LEVVEN = 65535 / 255

# Gateway mDNS (Section 1.3): Levven Gateway advertises when online
ZEROCONF_TYPE_LCAP = "_lcap._tcp.local."
