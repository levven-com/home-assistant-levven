"""Config flow for Levven integration."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import mqtt
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .const import (
    CONFIGURABLE_RECEIVER_TYPES,
    CONF_INCLUDE_TRANSMITTERS,
    DEVICE_TYPE_RECEIVER_CP2_4_5_CH1,
    DOMAIN,
    ENTITY_TYPE_LIGHT,
    ENTITY_TYPE_SWITCH,
    RESPONSE_TOPIC_PREFIX,
    RPC_TIMEOUT,
    TOPIC_GATEWAY_GETINFO,
    TOPIC_RECEIVER_GETINFO,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default="localhost"): str,
        vol.Required(CONF_PORT, default=1883): vol.Coerce(int),
        vol.Optional(CONF_USERNAME): str,
        vol.Optional(CONF_PASSWORD): str,
        vol.Optional("use_tls", default=False): bool,
        vol.Optional("include_transmitters_as_entities", default=True): bool,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    # Log a single high-level validation message; avoid verbose MQTT internals in normal logs.
    _LOGGER.info(
        "Validating Levven MQTT connection to %s:%s",
        data.get(CONF_HOST),
        data.get(CONF_PORT),
    )

    # Check if MQTT is configured
    if not mqtt.mqtt_config_entry_enabled(hass):
        _LOGGER.error("validate_input: MQTT is not configured in Home Assistant")
        raise CannotConnect("MQTT broker is not configured in Home Assistant")

    # Generate correlation ID and response topic
    correlation_id = str(uuid.uuid4())
    response_topic = f"{RESPONSE_TOPIC_PREFIX}/{correlation_id}"

    # Subscribe to response topic
    response_data = {}
    response_event = asyncio.Event()

    @callback
    def message_received(msg):
        """Handle response message. Per MQTT Design doc 4.2, response may be wrapped in "data"."""
        try:
            payload = json.loads(msg.payload)
            _LOGGER.debug("validate_input: received response on %s: %s", msg.topic, payload)
            # Gateway may send { "correlation_id": "...", "data": { ... } }
            response_data.update(payload.get("data", payload))
            response_event.set()
        except (json.JSONDecodeError, ValueError) as err:
            _LOGGER.error("validate_input: Invalid JSON in response: %s", err)

    # Subscribe to response topic (returns callable to unsubscribe)
    unsubscribe = await mqtt.async_subscribe(hass, response_topic, message_received, 1)

    # Brief delay so MQTT subscription is active before we publish (avoids race)
    await asyncio.sleep(1.0)

    # Publish gateway getinfo request (params empty; spec allows params wrapper)
    request_payload = {
        "params": {},
        "response_topic": response_topic,
        "correlation_id": correlation_id,
    }

    await mqtt.async_publish(
        hass,
        TOPIC_GATEWAY_GETINFO,
        json.dumps(request_payload),
        qos=1,
    )

    # Wait for response with timeout
    try:
        await asyncio.wait_for(response_event.wait(), timeout=RPC_TIMEOUT)
    except asyncio.TimeoutError:
        unsubscribe()
        _LOGGER.error(
            "validate_input: timeout after %ds. Ensure gateway/mock is running and connected to the same MQTT broker as HA (broker=%s:%s)",
            RPC_TIMEOUT,
            data.get(CONF_HOST),
            data.get(CONF_PORT),
        )
        raise CannotConnect(
            "Timeout waiting for gateway response. Is the gateway running and connected to the same MQTT broker as Home Assistant?"
        )

    # Unsubscribe from response topic
    unsubscribe()

    # Validate response
    if "gwid" not in response_data:
        _LOGGER.error("validate_input: response missing gwid: %s", response_data)
        raise InvalidAuth("Invalid gateway response: missing gwid")

    # Return info to be stored in the config entry
    return {
        "title": response_data.get("name", f"Levven Gateway {response_data.get('gwid', 'Unknown')}"),
        "gwid": response_data.get("gwid"),
        "gateway_name": response_data.get("name"),
        "receiver_count": response_data.get("receiver_count", 0),
        "transmitter_count": response_data.get("transmitter_count", 0),
    }


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Levven."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        super().__init__()
        self._discovery_info: dict[str, Any] | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_DATA_SCHEMA,
            )

        errors = {}

        try:
            info = await validate_input(self.hass, user_input)
        except CannotConnect as err:
            _LOGGER.warning("Cannot connect: %s", err)
            errors["base"] = "cannot_connect"
        except InvalidAuth as err:
            _LOGGER.warning("Invalid auth: %s", err)
            errors["base"] = "invalid_auth"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            # Check if this gateway is already configured
            await self.async_set_unique_id(info["gwid"])
            self._abort_if_unique_id_configured()

            data = {
                **user_input,
                "gwid": info["gwid"],
                "gateway_name": info.get("gateway_name") or info.get("title"),
                CONF_INCLUDE_TRANSMITTERS: user_input.get(
                    "include_transmitters_as_entities", True
                ),
            }
            data.pop("include_transmitters_as_entities", None)
            return self.async_create_entry(title=info["title"], data=data)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> OptionsFlowHandler:
        """Return the options flow handler. Base class sets flow.handler = entry_id so config_entry property works."""
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Levven integration options (e.g. Include Transmitters as entities)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage Levven options."""
        if user_input is not None:
            # Map form key to config key (form uses include_transmitters_as_entities for UI label)
            options_data = {CONF_INCLUDE_TRANSMITTERS: user_input.get("include_transmitters_as_entities", True)}
            result = self.async_create_entry(title="", data=options_data)
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return result

        current = self.config_entry.options.get(
            CONF_INCLUDE_TRANSMITTERS,
            self.config_entry.data.get(CONF_INCLUDE_TRANSMITTERS, True),
        )
        # Use a schema key that matches strings.json for reliable UI label (options.step.init.data.include_transmitters_as_entities)
        schema = vol.Schema(
            {
                vol.Required("include_transmitters_as_entities", default=current): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_discovery(
        self, discovery_info: dict[str, Any]
    ) -> FlowResult:
        """Handle device discovery. Device may already be added by coordinator; we still show form for optional name/type."""
        uid = discovery_info.get("uid")
        entry_id = discovery_info.get("entry_id")

        if not uid or not entry_id:
            return self.async_abort(reason="invalid_discovery_info")

        coordinator = None
        if DOMAIN in self.hass.data and entry_id in self.hass.data[DOMAIN]:
            coordinator = self.hass.data[DOMAIN][entry_id].get("coordinator")

        if not coordinator:
            return self.async_abort(reason="coordinator_not_found")

        self._discovery_info = discovery_info
        return await self.async_step_configure_device()

    async def async_step_configure_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure a discovered device."""
        if not self._discovery_info:
            return self.async_abort(reason="no_discovery_info")

        uid = self._discovery_info.get("uid")
        device_type = self._discovery_info.get("type")
        default_name = self._discovery_info.get("name", f"Levven Device {uid}")
        entry_id = self._discovery_info.get("entry_id")

        if not uid or not entry_id:
            return self.async_abort(reason="invalid_discovery_info")

        # Get device info from coordinator
        coordinator = None
        if DOMAIN in self.hass.data and entry_id in self.hass.data[DOMAIN]:
            coordinator = self.hass.data[DOMAIN][entry_id].get("coordinator")

        if not coordinator:
            return self.async_abort(reason="coordinator_not_found")

        # Prefer name from coordinator if device was already added
        device = coordinator.get_device(uid)
        default_name = (device.get("name") if device else None) or self._discovery_info.get("name", f"Levven Device {uid}")

        # Check if device is configurable (type 13)
        is_configurable = device_type in CONFIGURABLE_RECEIVER_TYPES
        has_level = self._discovery_info.get("level") is not None
        default_entity_type = ENTITY_TYPE_LIGHT if (is_configurable and has_level) else ENTITY_TYPE_SWITCH
        if device and "entity_type" in device:
            default_entity_type = device["entity_type"]

        if user_input is None:
            # Show configuration form
            schema_dict = {
                vol.Required("name", default=default_name): str,
            }

            if is_configurable:
                schema_dict[vol.Required("entity_type", default=default_entity_type)] = vol.In({
                    ENTITY_TYPE_LIGHT: "Light (Dimmer)",
                    ENTITY_TYPE_SWITCH: "Switch (On/Off)",
                })

            return self.async_show_form(
                step_id="configure_device",
                data_schema=vol.Schema(schema_dict),
                description_placeholders={
                    "uid": uid,
                    "type": str(device_type),
                },
            )

        # Store device configuration (device may already exist from coordinator; just update name/type)
        device_name = user_input.get("name", default_name)
        entity_type = user_input.get("entity_type", default_entity_type) if is_configurable else default_entity_type

        device = coordinator.get_device(uid)
        if not device:
            await coordinator._async_discover_device(uid)
            device = coordinator.get_device(uid)
        if device:
            device["name"] = device_name
            device["entity_type"] = entity_type

            # Store entity type preference in entity registry if configurable
            if is_configurable:
                entity_registry = er.async_get(self.hass)
                unique_id = f"levven_{coordinator.gwid}_{uid}"
                
                # Find existing entity or create options for future entity
                for entity_id, entity_entry in entity_registry.entities.items():
                    if entity_entry.unique_id == unique_id:
                        current_options = dict(entity_entry.options or {})
                        current_options.setdefault(DOMAIN, {})["entity_type"] = entity_type
                        entity_registry.async_update_entity_options(
                            entity_id, DOMAIN, current_options[DOMAIN]
                        )
                        break

        # Trigger entity creation/update
        coordinator.async_update_listeners()

        # Reload the integration to pick up the new entity
        await self.hass.config_entries.async_reload(entry_id)

        return self.async_abort(reason="device_configured")



class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
