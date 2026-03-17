"""DataUpdateCoordinator for Levven integration."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from homeassistant.components import mqtt, zeroconf
from homeassistant.config_entries import SOURCE_DISCOVERY
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from zeroconf import ServiceListener, ServiceBrowser

from .const import (
    BRIGHTNESS_SCALE_HA_TO_LEVVEN,
    BRIGHTNESS_SCALE_LEVVEN_TO_HA,
    CONFIGURABLE_RECEIVER_TYPES,
    CONF_INCLUDE_TRANSMITTERS,
    DEVICE_TYPE_TO_MODEL,
    LEVVEN_LEVEL_MAX,
    DIMMABLE_RECEIVER_TYPES,
    DOMAIN,
    ENTITY_TYPE_LIGHT,
    ENTITY_TYPE_SWITCH,
    EVENT_SWITCH_PRESSED,
    GATEWAY_TYPES,
    ONOFF_RECEIVER_TYPES,
    RESPONSE_TOPIC_PREFIX,
    RPC_TIMEOUT,
    TOPIC_LEVEL_GET,
    TOPIC_LEVEL_SET,
    TOPIC_NOTIFY_GATEWAY_INFO,
    TOPIC_NOTIFY_LEVEL,
    TOPIC_NOTIFY_ONOFF,
    TOPIC_NOTIFY_RECEIVER_DELETE,
    TOPIC_NOTIFY_RECEIVER_INFO,
    TOPIC_NOTIFY_RECEIVER_NEW,
    TOPIC_NOTIFY_RECEIVER_STATUS,
    TOPIC_NOTIFY_TRANSMITTER_ONOFF,
    TOPIC_ONOFF_GET,
    TOPIC_ONOFF_SET,
    TOPIC_RECEIVER_GETINFO,
    TOPIC_RECEIVERS_LIST,
    TRANSMITTER_PRESS_RELEASE_DELAY,
    TRANSMITTER_STATE_DOWN,
    TRANSMITTER_STATE_IDLE,
    TRANSMITTER_STATE_LONG_DOWN,
    TRANSMITTER_STATE_LONG_UP,
    TRANSMITTER_STATE_UP,
    TRANSMITTER_TYPES,
    TOPIC_NOTIFY_GATEWAY_BIRTH,
    TOPIC_NOTIFY_GATEWAY_DEATH,
    ZEROCONF_TYPE_LCAP,
)

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = 30  # seconds


class _LevvenGatewayListener(ServiceListener):
    """mDNS listener for _lcap._tcp.local; schedules coordinator updates on the event loop."""

    def __init__(self, hass: HomeAssistant, coordinator: "LevvenDataUpdateCoordinator") -> None:
        self.hass = hass
        self.coordinator = coordinator

    def add_service(self, zc: Any, type_: str, name: str) -> None:
        """Service added; resolve and check gwid on event loop. Called from zeroconf thread."""
        self.hass.add_job(self.coordinator._async_on_mdns_service_add(type_, name))

    def remove_service(self, zc: Any, type_: str, name: str) -> None:
        """Service removed. Called from zeroconf thread."""
        self.hass.add_job(self.coordinator._async_on_mdns_service_remove(type_, name))

    def update_service(self, zc: Any, type_: str, name: str) -> None:
        """Service updated; treat as add to refresh availability."""
        self.add_service(zc, type_, name)


class LevvenDataUpdateCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Class to manage fetching Levven data."""

    def __init__(self, hass: HomeAssistant, config_entry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,  # We update via notifications, not polling
        )
        self.config_entry = config_entry
        self.gwid = config_entry.data.get("gwid", "unknown")
        self.gateway_name = config_entry.data.get("gateway_name", "Levven Gateway")
        self._devices: dict[str, dict[str, Any]] = {}
        self._pending_requests: dict[str, asyncio.Event] = {}
        self._pending_responses: dict[str, dict[str, Any]] = {}
        self._subscriptions: list[str] = []
        # When True, discover transmitters (wall switches) as entities for automations
        self._include_transmitters: bool = config_entry.options.get(
            CONF_INCLUDE_TRANSMITTERS,
            config_entry.data.get(CONF_INCLUDE_TRANSMITTERS, True),
        )
        # Tri-state per transmitter: idle | up | down (future: long_up, long_down)
        self._transmitter_state: dict[str, str] = {}
        # Timer handles for scheduled reset-to-idle per transmitter (call handle.cancel() to cancel)
        self._transmitter_reset_handles: dict[str, asyncio.TimerHandle] = {}
        # Gateway presence (MQTT birth/death + mDNS fallback)
        self._gateway_available: bool = True  # assume available until presence says otherwise
        self._mdns_services: set[str] = set()  # service names that reported our gwid
        self._mdns_browser: ServiceBrowser | None = None

    @property
    def gateway_available(self) -> bool:
        """True if gateway has been seen via MQTT birth (or mDNS / no explicit presence configured)."""
        return self._gateway_available

    async def async_setup(self) -> None:
        """Set up the coordinator and start listening for notifications and presence."""
        # Subscribe to all notification topics
        await self._async_subscribe_notifications()

        # Start mDNS browser for gateway presence (_lcap._tcp.local) as a fallback to MQTT birth/death
        await self._async_start_mdns_browser()

        # Perform initial device discovery
        await self.async_discover_devices()

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Return current device state for coordinator refresh. Data is updated via MQTT notifications."""
        return self._devices.copy()

    async def _async_start_mdns_browser(self) -> None:
        """Start browsing for _lcap._tcp.local to track gateway online presence."""
        try:
            zc = await zeroconf.async_get_instance(self.hass)
            listener = _LevvenGatewayListener(self.hass, self)
            self._mdns_browser = ServiceBrowser(zc, ZEROCONF_TYPE_LCAP, listener)
            _LOGGER.debug("Started mDNS browser for %s", ZEROCONF_TYPE_LCAP)
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning("Could not start mDNS browser for gateway presence: %s", err)
            # Leave _gateway_available as True so entities remain available

    async def _async_on_mdns_service_add(self, service_type: str, name: str) -> None:
        """Handle mDNS service added: resolve and check gwid."""
        try:
            zc = await zeroconf.async_get_instance(self.hass)
            info = await self.hass.async_add_executor_job(zc.get_service_info, service_type, name)
            if not info or not info.properties:
                return
            gwid_raw = info.properties.get("gwid")
            if gwid_raw is None:
                return
            gwid = gwid_raw.decode("utf-8", errors="replace") if isinstance(gwid_raw, bytes) else str(gwid_raw)
            if gwid != self.gwid:
                return
            self._mdns_services.add(name)
            if not self._gateway_available:
                self._gateway_available = True
                _LOGGER.info("Gateway %s seen on network (mDNS)", self.gwid)
            self.async_update_listeners()
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.debug("mDNS resolve for %s: %s", name, err)

    async def _async_on_mdns_service_remove(self, service_type: str, name: str) -> None:
        """Handle mDNS service removed."""
        if name not in self._mdns_services:
            return
        self._mdns_services.discard(name)
        if not self._mdns_services and self._gateway_available:
            self._gateway_available = False
            _LOGGER.warning("Gateway %s no longer seen on network (mDNS)", self.gwid)
            self.async_update_listeners()

    def async_stop(self) -> None:
        """Stop mDNS browser and cancel transmitter reset timers when config entry is unloaded."""
        for handle in self._transmitter_reset_handles.values():
            try:
                handle.cancel()
            except Exception:  # pylint: disable=broad-except
                pass
        self._transmitter_reset_handles.clear()
        if self._mdns_browser is not None:
            try:
                self._mdns_browser.cancel()
            except Exception:  # pylint: disable=broad-except
                pass
            self._mdns_browser = None

    def _get_entity_type_preference(self, uid: str, device_type: int) -> str | None:
        """Get entity type preference from entity registry for configurable devices."""
        entity_registry = er.async_get(self.hass)
        unique_id = f"levven_{self.gwid}_{uid}"
        
        # Check for existing entity (could be light or switch)
        for entity_id in entity_registry.entities:
            entity_entry = entity_registry.entities[entity_id]
            if entity_entry.unique_id == unique_id:
                # Check entity options for preference
                if entity_entry.options:
                    entity_type_pref = entity_entry.options.get(DOMAIN, {}).get("entity_type")
                    if entity_type_pref in (ENTITY_TYPE_LIGHT, ENTITY_TYPE_SWITCH):
                        return entity_type_pref
                # If entity exists, infer from platform
                if entity_entry.platform == "light":
                    return ENTITY_TYPE_LIGHT
                if entity_entry.platform == "switch":
                    return ENTITY_TYPE_SWITCH
        
        return None

    async def _async_subscribe_notifications(self) -> None:
        """Subscribe to all notification topics.
        V2 gateways use only notify/receiver/info for level; notify/level is kept for V1 backward compatibility.
        Also subscribe to MQTT presence topics (birth/death) for gateway availability.
        """
        topics = [
            (TOPIC_NOTIFY_GATEWAY_INFO, self._handle_gateway_info),
            (TOPIC_NOTIFY_GATEWAY_BIRTH, self._handle_gateway_birth),
            (TOPIC_NOTIFY_GATEWAY_DEATH, self._handle_gateway_death),
            (TOPIC_NOTIFY_LEVEL, self._handle_level),
            (TOPIC_NOTIFY_ONOFF, self._handle_onoff),
            (TOPIC_NOTIFY_RECEIVER_NEW, self._handle_receiver_new),
            (TOPIC_NOTIFY_RECEIVER_DELETE, self._handle_receiver_delete),
            (TOPIC_NOTIFY_RECEIVER_INFO, self._handle_receiver_info),
            (TOPIC_NOTIFY_RECEIVER_STATUS, self._handle_receiver_status),
            (TOPIC_NOTIFY_TRANSMITTER_ONOFF, self._handle_transmitter_onoff),
        ]

        for topic, handler in topics:
            await mqtt.async_subscribe(
                self.hass,
                topic,
                lambda msg, h=handler: self._handle_notification(h, msg),
                1,
            )
            self._subscriptions.append(topic)
            # Subscriptions are stable; no need to log every topic in normal operation.

    @callback
    def _handle_notification(
        self, handler: callable, msg: mqtt.ReceiveMessage
    ) -> None:
        """Handle incoming notification message. Runs on MQTT thread; schedules handler on event loop for thread safety."""
        try:
            payload = json.loads(msg.payload)
            # Real gateway wraps notify payloads in {"data":{...}}; spec implied flat.
            payload = payload.get("data", payload)
            # Schedule handler on the event loop via call_soon_threadsafe so it always runs there
            # (add_job can run sync callables in an executor, causing async_fire/async_update_listeners to fail)
            self.hass.loop.call_soon_threadsafe(
                self._schedule_notification_handler_on_loop,
                handler,
                payload,
            )
        except (json.JSONDecodeError, ValueError) as err:
            _LOGGER.error("Invalid JSON in notification %s: %s", msg.topic, err)
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.exception("Error handling notification %s: %s", msg.topic, err)

    def _schedule_notification_handler_on_loop(
        self, handler: callable, payload: dict[str, Any]
    ) -> None:
        """Run on the event loop (from call_soon_threadsafe). Schedules async handler so all HA APIs are safe."""
        self.hass.async_create_task(
            self._async_invoke_notification_handler(handler, payload)
        )

    async def _async_invoke_notification_handler(
        self, handler: callable, payload: dict[str, Any]
    ) -> None:
        """Invoke the notification handler on the event loop (async so we're definitely on it)."""
        try:
            handler(payload)
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.exception("Error in notification handler: %s", err)

    @callback
    def _handle_gateway_info(self, payload: dict[str, Any]) -> None:
        """Handle gateway info notification."""
        # Gateway may send periodic empty payloads; avoid logging every update at debug level.
        # Update gateway info if needed
        if "gwid" in payload:
            self.gwid = payload["gwid"]
        if "name" in payload:
            self.gateway_name = payload.get("name", "Levven Gateway")

    @callback
    def _handle_gateway_birth(self, payload: dict[str, Any]) -> None:
        """Handle gateway MQTT birth (presence) message.

        Any message on the configured Presence Topic is treated as 'gateway online';
        payload contents are not required.
        """
        if not self._gateway_available:
            _LOGGER.info("Gateway %s marked online from MQTT presence (birth topic)", self.gwid)
        self._gateway_available = True
        self.async_update_listeners()

    @callback
    def _handle_gateway_death(self, payload: dict[str, Any]) -> None:
        """Handle gateway MQTT last-will (death) message.

        Any message on the configured Last Will Topic is treated as 'gateway offline';
        payload contents are not required.
        """
        if self._gateway_available:
            _LOGGER.warning("Gateway %s marked offline from MQTT last will (death topic)", self.gwid)
        self._gateway_available = False
        self.async_update_listeners()

    @callback
    def _handle_level(self, payload: dict[str, Any]) -> None:
        """Handle level notification. Only update when level is present and in valid range (0-65535)."""
        uid = payload.get("uid")
        if not uid:
            return

        level = payload.get("level")
        if level is not None and isinstance(level, (int, float)) and 0 <= level <= LEVVEN_LEVEL_MAX:
            if uid in self._devices:
                self._devices[uid]["level"] = int(level)
                self._devices[uid]["is_on"] = level > 0
                self.async_update_listeners()

    @callback
    def _handle_onoff(self, payload: dict[str, Any]) -> None:
        """Handle on/off notification. Only update when is_on is present in payload."""
        uid = payload.get("uid")
        if not uid:
            return

        if "is_on" not in payload:
            return
        is_on = payload.get("is_on", False)
        if uid in self._devices:
            self._devices[uid]["is_on"] = is_on
            self.async_update_listeners()

    @callback
    def _handle_receiver_new(self, payload: dict[str, Any]) -> None:
        """Handle receiver new notification. Schedules one discovery task per UID (deduped)."""
        uid = payload.get("uid")
        device_type = payload.get("type")
        if not uid:
            return
        self.hass.async_create_task(self._async_handle_receiver_new_deduped(uid, device_type))

    async def _async_handle_receiver_new_deduped(self, uid: str, device_type: int) -> None:
        """Ensure only one discovery task runs per UID globally (same UID, duplicate messages or two coordinators)."""
        domain_data = self.hass.data.setdefault(DOMAIN, {})
        if "_discovery_lock" not in domain_data:
            domain_data["_discovery_lock"] = asyncio.Lock()
        if "_discovery_uids" not in domain_data:
            domain_data["_discovery_uids"] = set()
        async with domain_data["_discovery_lock"]:
            if uid in domain_data["_discovery_uids"]:
                return
            domain_data["_discovery_uids"].add(uid)
        _LOGGER.info("New receiver discovered: %s (type: %s)", uid, device_type)
        try:
            await self._async_trigger_discovery_flow(uid, device_type)
        finally:
            domain_data.get("_discovery_uids", set()).discard(uid)

    @callback
    def _handle_receiver_delete(self, payload: dict[str, Any]) -> None:
        """Handle receiver delete notification. Remove from coordinator and from HA device/entity registry."""
        uid = payload.get("uid")
        if not uid:
            return

        if uid not in self._devices:
            return

        _LOGGER.info("Receiver deleted: %s", uid)
        del self._devices[uid]

        # Remove device (and its entities) from HA so the UI updates
        dev_reg = dr.async_get(self.hass)
        device = dev_reg.async_get_device(identifiers={(DOMAIN, f"{self.gwid}_{uid}")})
        if device:
            dev_reg.async_remove_device(device.id)
        else:
            # Fallback: remove entities by unique_id in case device was already gone
            entity_reg = er.async_get(self.hass)
            unique_id = f"levven_{self.gwid}_{uid}"
            for platform in ("light", "switch"):
                if entity_id := entity_reg.async_get_entity_id(platform, DOMAIN, unique_id):
                    entity_reg.async_remove(entity_id)

        self.async_update_listeners()

    @callback
    def _handle_receiver_info(self, payload: dict[str, Any]) -> None:
        """Handle receiver info notification (PDF Appendix A: may include dimmable).
        If uid not in _devices and payload has type, treat as new receiver (gateway push after receiver/new).
        Otherwise only update level/is_on when payload contains valid level (0-65535) or is_on.
        """
        uid = payload.get("uid")
        if not uid:
            return

        if uid not in self._devices:
            # New receiver: add from payload (same process as transmitters - gateway pushes info)
            if payload.get("type") is not None:
                self._add_receiver_device_from_payload(uid, payload)
            return

        # Existing receiver: update fields; if name changed, propagate to device/entity registry
        device = self._devices.get(uid, {})
        old_name = device.get("name")

        updates: dict[str, Any] = {}
        if "name" in payload:
            updates["name"] = payload["name"]
        if "type" in payload:
            updates["type"] = payload["type"]
        if "icon" in payload:
            updates["icon"] = payload["icon"]
        if "dimmable" in payload:
            updates["dimmable"] = payload["dimmable"]
        # Only update level when present and in valid range (ignore uid-only messages)
        level = payload.get("level")
        if level is not None and isinstance(level, (int, float)) and 0 <= level <= LEVVEN_LEVEL_MAX:
            updates["level"] = int(level)
            updates["is_on"] = level > 0
        elif "is_on" in payload:
            updates["is_on"] = payload["is_on"]

        # If dimmable changed in Levven app (enable/disable dimming), swap entity type (light <-> switch)
        if "dimmable" in payload:
            merged = {**device, **updates}
            new_entity_type = self._compute_entity_type(uid, merged)
            old_entity_type = device.get("entity_type")
            if new_entity_type and old_entity_type and new_entity_type != old_entity_type:
                updates["entity_type"] = new_entity_type
                # Update coordinator state first so debounced listeners see new type before we notify
                self._devices[uid].update(updates)
                entity_reg = er.async_get(self.hass)
                unique_id = f"levven_{self.gwid}_{uid}"
                entity_id = entity_reg.async_get_entity_id(old_entity_type, DOMAIN, unique_id)
                if entity_id:
                    entity_reg.async_remove(entity_id)
                    _LOGGER.info(
                        "Entity type changed for %s: %s -> %s (dimmable=%s)",
                        uid, old_entity_type, new_entity_type, payload.get("dimmable"),
                    )

        # If the name changed in Levven app, update device + entity registry so HA shows the new name.
        new_name = updates.get("name")
        if new_name and new_name != old_name:
            dev_reg = dr.async_get(self.hass)
            device_entry = dev_reg.async_get_device(
                identifiers={(DOMAIN, f"{self.gwid}_{uid}")}
            )
            if device_entry:
                dev_reg.async_update_device(device_entry.id, name=new_name)

            entity_reg = er.async_get(self.hass)
            unique_id = f"levven_{self.gwid}_{uid}"
            for platform in ("light", "switch"):
                entity_id = entity_reg.async_get_entity_id(platform, DOMAIN, unique_id)
                if not entity_id:
                    continue
                entity_entry = entity_reg.async_get(entity_id)
                if not entity_entry:
                    continue
                # Only override name if user has not explicitly renamed it (name is None)
                # or if it still matches the old device name.
                if entity_entry.name is None or (
                    old_name and entity_entry.name == old_name
                ):
                    entity_reg.async_update_entity(entity_id, name=new_name)

        if updates:
            self._devices[uid].update(updates)
            self.async_update_listeners()

    def _compute_entity_type(self, uid: str, data: dict[str, Any]) -> str | None:
        """Compute entity_type (light/switch) from device/payload data. Returns None for gateways/transmitters."""
        device_type = data.get("type", 0)
        if device_type in GATEWAY_TYPES or device_type in TRANSMITTER_TYPES:
            return None
        if device_type in CONFIGURABLE_RECEIVER_TYPES:
            # When dimmable is in payload, use it (user changed in Levven app); else use preference
            if "dimmable" in data:
                return ENTITY_TYPE_LIGHT if data.get("dimmable") else ENTITY_TYPE_SWITCH
            entity_type = self._get_entity_type_preference(uid, device_type)
            if entity_type is not None:
                return entity_type
            has_level = "level" in data and data.get("level") is not None
            return ENTITY_TYPE_LIGHT if has_level else ENTITY_TYPE_SWITCH
        if "dimmable" in data:
            return ENTITY_TYPE_LIGHT if data.get("dimmable") else ENTITY_TYPE_SWITCH
        is_dimmable = device_type in DIMMABLE_RECEIVER_TYPES
        has_level = "level" in data and data.get("level") is not None
        return ENTITY_TYPE_LIGHT if (is_dimmable and has_level) else ENTITY_TYPE_SWITCH

    def _add_receiver_device_from_payload(self, uid: str, payload: dict[str, Any]) -> bool:
        """Add a receiver to _devices from getinfo/receiver/info payload. Returns True if added or updated."""
        device_type = payload.get("type", 0)
        if device_type in GATEWAY_TYPES or device_type in TRANSMITTER_TYPES:
            return False
        entity_type = self._compute_entity_type(uid, payload)
        self._devices[uid] = {
            "uid": uid,
            "name": payload.get("name", f"Levven Device {uid}"),
            "type": device_type,
            "is_on": payload.get("is_on", False),
            "level": payload.get("level"),
            "icon": payload.get("icon"),
            "dimmable": payload.get("dimmable"),
            "reachable": True,
            "entity_type": entity_type,
        }
        _LOGGER.info(
            "Discovered device %s: %s (type: %s, entity: %s)",
            uid, self._devices[uid]["name"], device_type, entity_type,
        )
        self.async_update_listeners()
        return True

    @callback
    def _handle_receiver_status(self, payload: dict[str, Any]) -> None:
        """Handle receiver status notification."""
        uid = payload.get("uid")
        if not uid:
            return

        reachable = payload.get("reachable", True)
        if uid in self._devices:
            self._devices[uid]["reachable"] = reachable
            # Update entity availability
            self.async_update_listeners()

    @callback
    def _handle_transmitter_onoff(self, payload: dict[str, Any]) -> None:
        """Handle transmitter on/off notification. Tri-state: up (is_on true), down (is_on false), idle after delay.
        Future: payload may include long_press for long_up/long_down.
        """
        tuid = payload.get("tuid")
        is_on = payload.get("is_on", False)
        long_press = payload.get("long_press", False)  # reserved for future Levven API
        if not tuid:
            return

        # Cancel any pending reset-to-idle for this transmitter
        if tuid in self._transmitter_reset_handles:
            self._transmitter_reset_handles.pop(tuid).cancel()

        # Set tri-state: up = pressed up, down = pressed down; future: long_press -> long_up/long_down
        if long_press:
            state = TRANSMITTER_STATE_LONG_UP if is_on else TRANSMITTER_STATE_LONG_DOWN
        else:
            state = TRANSMITTER_STATE_UP if is_on else TRANSMITTER_STATE_DOWN
        self._transmitter_state[tuid] = state

        _LOGGER.debug("Transmitter %s state: %s", tuid, state)

        # If option enabled, discover transmitter on first message (no discovery API for transmitters)
        newly_discovered = False
        if self._include_transmitters and tuid not in self._devices:
            self._devices[tuid] = {
                "uid": tuid,
                "name": f"Levven Transmitter {tuid}",
                "type": 2,  # Generic switch type; we don't get type from notify message
                "entity_type": "transmitter",
                "reachable": True,
            }
            _LOGGER.info("Discovered transmitter from MQTT: %s", tuid)
            newly_discovered = True
            # Create device first, then notify listeners (avoids "unknown config entry" when adding entity)
            self.hass.async_create_task(
                self._async_ensure_transmitter_device_then_notify(tuid)
            )

        # Fire HA event for automation
        self.hass.bus.async_fire(
            EVENT_SWITCH_PRESSED,
            {
                "tuid": tuid,
                "is_on": is_on,
                "state": state,
                "gateway_id": self.gwid,
            },
        )
        # Schedule return to idle after delay (press events are momentary)
        handle = self.hass.loop.call_later(
            TRANSMITTER_PRESS_RELEASE_DELAY,
            lambda: self._reset_transmitter_to_idle(tuid),
        )
        self._transmitter_reset_handles[tuid] = handle
        if not newly_discovered:
            self.async_update_listeners()

    @callback
    def _reset_transmitter_to_idle(self, tuid: str) -> None:
        """Reset transmitter state to idle after press release delay."""
        self._transmitter_reset_handles.pop(tuid, None)
        self._transmitter_state[tuid] = TRANSMITTER_STATE_IDLE
        self.async_update_listeners()

    async def _async_ensure_transmitter_device_then_notify(self, tuid: str) -> None:
        """Create transmitter device in device registry (so entity add finds a valid config entry), then notify listeners."""
        device = self._devices.get(tuid)
        if not device or device.get("entity_type") != "transmitter":
            return
        dev_reg = dr.async_get(self.hass)
        # Same identifiers/name/model as LevvenTransmitterSensor so entity platform finds this device
        kwargs: dict[str, Any] = {
            "config_entry_id": self.config_entry.entry_id,
            "identifiers": {(DOMAIN, f"{self.gwid}_tx_{tuid}")},
            "name": device.get("name", f"Levven Transmitter {tuid}"),
            "manufacturer": "Levven",
            "model": DEVICE_TYPE_TO_MODEL.get(device.get("type", 0), "Type 2"),
        }
        if self.gwid and self.gwid != "unknown":
            kwargs["via_device"] = (DOMAIN, self.gwid)
        try:
            dev_reg.async_get_or_create(**kwargs)
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning(
                "Could not create device for transmitter %s (skipping entity): %s",
                tuid,
                err,
            )
            return
        self.async_update_listeners()

    async def async_discover_devices(self) -> None:
        """Discover all receivers."""
        try:
            # Get list of receivers
            response = await self.async_publish_rpc(
                TOPIC_RECEIVERS_LIST, {}, wait_response=True
            )

            if not response or "uids" not in response:
                _LOGGER.warning("No receivers found or invalid response")
                return

            uids = response.get("uids", [])
            _LOGGER.info("Found %d receivers", len(uids))

            # Discover each receiver
            for uid in uids:
                await self._async_discover_device(uid)

        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.exception("Error during device discovery: %s", err)
            raise UpdateFailed(f"Error discovering devices: {err}") from err

    async def _async_discover_device(self, uid: str, response: dict[str, Any] | None = None) -> None:
        """Discover a single device. If response is provided, use it; otherwise request via RPC."""
        try:
            if response is None:
                response = await self.async_publish_rpc(
                    TOPIC_RECEIVER_GETINFO, {"uid": uid}, wait_response=True
                )

            if not response or "uid" not in response:
                _LOGGER.warning(
                    "Invalid or missing response for device %s (timeout or gateway may not support receiver/getinfo)",
                    uid,
                )
                return

            device_type = response.get("type", 0)
            if device_type in GATEWAY_TYPES or device_type in TRANSMITTER_TYPES:
                _LOGGER.debug("Skipping device %s (type %s)", uid, device_type)
                return

            self._add_receiver_device_from_payload(uid, response)

        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.exception("Error discovering device %s: %s", uid, err)

    async def _async_trigger_discovery_flow(self, uid: str, device_type: int) -> None:
        """Trigger discovery flow for a newly discovered device."""
        try:
            # Get device info first
            response = await self.async_publish_rpc(
                TOPIC_RECEIVER_GETINFO, {"uid": uid}, wait_response=True
            )

            if not response or "uid" not in response:
                _LOGGER.warning("Could not get info for discovered device %s", uid)
                # Fall back to auto-discovery without flow
                await self._async_discover_device(uid)
                return

            # Check if device should be shown in discovery flow
            # Skip gateways and transmitters
            if device_type in GATEWAY_TYPES or device_type in TRANSMITTER_TYPES:
                await self._async_discover_device(uid, response=response)
                return

            # Add device immediately so it shows up in HA (listener adds entity, same as transmitters)
            await self._async_discover_device(uid, response=response)

            # Create discovery info and trigger optional "Configure device" flow (user can set name/entity type)
            discovery_info = {
                "uid": uid,
                "type": device_type,
                "name": response.get("name", f"Levven Device {uid}"),
                "level": response.get("level"),
                "is_on": response.get("is_on", False),
                "icon": response.get("icon"),
                "entry_id": self.config_entry.entry_id,
            }

            await self.hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_DISCOVERY},
                data=discovery_info,
            )
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.exception("Error triggering discovery flow for device %s: %s", uid, err)
            # Fall back to auto-discovery (in case we hadn't added yet)
            await self._async_discover_device(uid)

    async def async_publish_rpc(
        self,
        topic: str,
        payload: dict[str, Any],
        wait_response: bool = False,
        timeout: float = RPC_TIMEOUT,
    ) -> dict[str, Any] | None:
        """Publish an RPC request and optionally wait for response."""
        correlation_id = str(uuid.uuid4())
        response_topic = f"{RESPONSE_TOPIC_PREFIX}/{correlation_id}"

        # Levven spec: wrap method params in "params"; response_topic and correlation_id at top level
        request_payload = {
            "params": dict(payload),
            "response_topic": response_topic,
            "correlation_id": correlation_id,
        }

        if wait_response:
            # Set up response waiting
            response_event = asyncio.Event()
            self._pending_requests[correlation_id] = response_event
            self._pending_responses[correlation_id] = {}

            @callback
            def message_received(msg: mqtt.ReceiveMessage) -> None:
                """Handle response message. Per MQTT Design doc 4.2, response may be wrapped in "data"."""
                try:
                    payload = json.loads(msg.payload)
            # RPC responses are frequent; avoid logging full payloads by default.
                    # Gateway may send { "correlation_id": "...", "data": { ... } }
                    self._pending_responses[correlation_id] = payload.get("data", payload)
                    response_event.set()
                except (json.JSONDecodeError, ValueError) as err:
                    _LOGGER.error("Invalid JSON in response: %s", err)
                    response_event.set()

            # Subscribe to response topic (returns callable to unsubscribe)
            unsubscribe_response = await mqtt.async_subscribe(
                self.hass, response_topic, message_received, 1
            )
            # Do not log every RPC subscription in normal operation.
            await asyncio.sleep(0.5)  # Allow subscription to register before publish

        # Publish request
        # Do not log every RPC publish in normal operation.
        await mqtt.async_publish(
            self.hass,
            topic,
            json.dumps(request_payload),
            qos=1,
        )

        if wait_response:
            # Wait for response
            try:
                await asyncio.wait_for(response_event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                _LOGGER.warning("Timeout waiting for response to %s", topic)
                return None
            finally:
                # Clean up
                if correlation_id in self._pending_requests:
                    del self._pending_requests[correlation_id]
                if correlation_id in self._pending_responses:
                    response = self._pending_responses.pop(correlation_id)
                    # Unsubscribe from response topic
                    unsubscribe_response()
                    return response

        return None

    async def async_set_onoff(self, uid: str, is_on: bool) -> None:
        """Set device on/off state."""
        await self.async_publish_rpc(
            TOPIC_ONOFF_SET, {"uid": uid, "is_on": is_on}, wait_response=False
        )

    async def async_set_level(self, uid: str, level: int) -> None:
        """Set device level (0-65535, 16-bit). When level > 0, also send is_on: true so the light turns on."""
        level = max(0, min(LEVVEN_LEVEL_MAX, level))
        await self.async_publish_rpc(
            TOPIC_LEVEL_SET, {"uid": uid, "level": level}, wait_response=False
        )
        if level > 0:
            await self.async_set_onoff(uid, True)

    async def async_get_onoff(self, uid: str) -> bool | None:
        """Get device on/off state."""
        response = await self.async_publish_rpc(
            TOPIC_ONOFF_GET, {"uid": uid}, wait_response=True
        )
        if response:
            return response.get("is_on")
        return None

    async def async_get_level(self, uid: str) -> int | None:
        """Get device level (0-65535)."""
        response = await self.async_publish_rpc(
            TOPIC_LEVEL_GET, {"uid": uid}, wait_response=True
        )
        if response:
            return response.get("level")
        return None

    def get_device(self, uid: str) -> dict[str, Any] | None:
        """Get device info by UID."""
        return self._devices.get(uid)

    def get_transmitter_state(self, uid: str) -> str:
        """Return tri-state for transmitter: idle, up, down (future: long_up, long_down)."""
        return self._transmitter_state.get(uid, TRANSMITTER_STATE_IDLE)

    def get_devices(self) -> dict[str, dict[str, Any]]:
        """Get all devices."""
        return self._devices.copy()

    def get_devices_by_type(self, entity_type: str) -> list[dict[str, Any]]:
        """Get devices filtered by entity type."""
        return [
            device
            for device in self._devices.values()
            if device.get("entity_type") == entity_type
        ]

    def levven_to_ha_brightness(self, level: int | None) -> int | None:
        """Convert Levven level (0-65535) to HA brightness (0-255)."""
        if level is None:
            return None
        return int(level * BRIGHTNESS_SCALE_LEVVEN_TO_HA)

    def ha_to_levven_brightness(self, brightness: int | None) -> int | None:
        """Convert HA brightness (0-255) to Levven level (0-65535)."""
        if brightness is None:
            return None
        return int(brightness * BRIGHTNESS_SCALE_HA_TO_LEVVEN)
