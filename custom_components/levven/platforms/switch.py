"""Switch platform for Levven integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import DEVICE_TYPE_TO_MODEL, DOMAIN
from ..coordinator import LevvenDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# Device type to model name mapping (use central const for full table)
DEVICE_TYPE_MODELS = DEVICE_TYPE_TO_MODEL


@callback
def _register_receiver_listener(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    coordinator: LevvenDataUpdateCoordinator,
) -> None:
    """Register a listener so we add switch entities when new receivers appear from MQTT (same as transmitters)."""
    _pending: list = []  # [TimerHandle] for debounce
    added_uids: set[str] = set()  # tracks uids added *this session*; entity registry persists across restarts so it can't be used for this

    @callback
    def _add_new_switches() -> None:
        if hass.config_entries.async_get_entry(config_entry.entry_id) is None:
            return
        devices = coordinator.get_devices_by_type("switch")
        new_entities = []
        for device in devices:
            uid = device["uid"]
            if uid in added_uids:
                continue
            added_uids.add(uid)
            new_entities.append(LevvenSwitch(coordinator, device))
        if new_entities:
            async_add_entities(new_entities)

    @callback
    def _debounced_add() -> None:
        _pending.clear()
        _add_new_switches()

    @callback
    def _on_update() -> None:
        for handle in _pending:
            try:
                handle.cancel()
            except Exception:  # pylint: disable=broad-except
                pass
        _pending.append(hass.loop.call_later(0.3, _debounced_add))

    _add_new_switches()
    coordinator.async_add_listener(_on_update)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Levven switch entities. New receivers added when discovered via MQTT (same as transmitters)."""
    coordinator: LevvenDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]["coordinator"]

    _register_receiver_listener(hass, config_entry, async_add_entities, coordinator)


class LevvenSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of a Levven switch."""

    def __init__(
        self,
        coordinator: LevvenDataUpdateCoordinator,
        device: dict[str, Any],
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._uid = device["uid"]
        self._device = device
        self._attr_unique_id = f"levven_{coordinator.gwid}_{device['uid']}"
        self._attr_name = device.get("name", f"Levven Switch {device['uid']}")

        # Device info: show product model instead of type number
        device_type = device.get("type", 0)
        model = DEVICE_TYPE_MODELS.get(device_type, f"Type {device_type}")
        device_info_kw: dict[str, Any] = {
            "identifiers": {(DOMAIN, f"{coordinator.gwid}_{device['uid']}")},
            "name": device.get("name", f"Levven Device {device['uid']}"),
            "manufacturer": "Levven",
            "model": model,
        }
        if coordinator.gwid and coordinator.gwid != "unknown":
            device_info_kw["via_device"] = (DOMAIN, coordinator.gwid)
        self._attr_device_info = DeviceInfo(**device_info_kw)

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        device = self.coordinator.get_device(self._uid)
        if device:
            return device.get("is_on", False)
        return False

    @property
    def available(self) -> bool:
        """Return if entity is available (gateway seen via mDNS and device reachable)."""
        if not self.coordinator.gateway_available:
            return False
        device = self.coordinator.get_device(self._uid)
        if device:
            return device.get("reachable", True)
        return False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self.coordinator.async_set_onoff(self._uid, True)
        # Update state immediately
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self.coordinator.async_set_onoff(self._uid, False)
        # Update state immediately
        await self.coordinator.async_request_refresh()

    async def async_update(self) -> None:
        """Update the switch state."""
        # Get current state
        is_on = await self.coordinator.async_get_onoff(self._uid)

        # Update device in coordinator
        device = self.coordinator.get_device(self._uid)
        if device and is_on is not None:
            device["is_on"] = is_on

        self.async_write_ha_state()
