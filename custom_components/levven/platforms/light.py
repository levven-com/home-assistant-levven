"""Light platform for Levven integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
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
    """Register a listener so we add light entities when new receivers appear from MQTT (same as transmitters)."""
    _pending: list = []  # [TimerHandle] for debounce

    @callback
    def _add_new_lights() -> None:
        if hass.config_entries.async_get_entry(config_entry.entry_id) is None:
            return
        devices = coordinator.get_devices_by_type("light")
        entity_reg = async_get_entity_registry(hass)
        new_entities = []
        for device in devices:
            uid = device["uid"]
            unique_id = f"levven_{coordinator.gwid}_{uid}"
            if entity_reg.async_get_entity_id("light", DOMAIN, unique_id):
                continue
            new_entities.append(LevvenLight(coordinator, device))
        if new_entities:
            async_add_entities(new_entities)

    @callback
    def _debounced_add() -> None:
        _pending.clear()
        _add_new_lights()

    @callback
    def _on_update() -> None:
        # Debounce: schedule one run shortly so multiple devices added in quick succession get one pass
        for handle in _pending:
            try:
                handle.cancel()
            except Exception:  # pylint: disable=broad-except
                pass
        _pending.append(hass.loop.call_later(0.3, _debounced_add))

    _add_new_lights()
    coordinator.async_add_listener(_on_update)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Levven light entities. New receivers added when discovered via MQTT (same as transmitters)."""
    coordinator: LevvenDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]["coordinator"]

    _register_receiver_listener(hass, config_entry, async_add_entities, coordinator)


class LevvenLight(CoordinatorEntity, LightEntity):
    """Representation of a Levven light."""

    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def _device_dimmable(self) -> bool:
        """True if the device supports brightness (avoids level/set on non-dimmable)."""
        device = self.coordinator.get_device(self._uid)
        return bool(device.get("dimmable")) if device else False

    @property
    def supported_color_modes(self) -> set[str]:
        """On/off only when device is not dimmable (e.g. after role change in Levven app)."""
        if self._device_dimmable():
            return {ColorMode.BRIGHTNESS}
        return {ColorMode.ONOFF}

    @property
    def color_mode(self) -> str:
        """Match supported_color_modes so UI does not show brightness when not dimmable."""
        if self._device_dimmable():
            return ColorMode.BRIGHTNESS
        return ColorMode.ONOFF

    def __init__(
        self,
        coordinator: LevvenDataUpdateCoordinator,
        device: dict[str, Any],
    ) -> None:
        """Initialize the light."""
        super().__init__(coordinator)
        self._uid = device["uid"]
        self._device = device
        self._attr_unique_id = f"levven_{coordinator.gwid}_{device['uid']}"
        self._attr_name = device.get("name", f"Levven Light {device['uid']}")

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
        """Return true if light is on."""
        device = self.coordinator.get_device(self._uid)
        if device:
            return device.get("is_on", False)
        return False

    @property
    def brightness(self) -> int | None:
        """Return the brightness of the light."""
        device = self.coordinator.get_device(self._uid)
        if device:
            level = device.get("level")
            if level is not None:
                return self.coordinator.levven_to_ha_brightness(level)
        return None

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
        """Turn the light on."""
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        if brightness is not None and self._device_dimmable():
            # Set brightness first (this also turns on)
            level = self.coordinator.ha_to_levven_brightness(brightness)
            await self.coordinator.async_set_level(self._uid, level)
        else:
            # Just turn on (or device is non-dimmable)
            await self.coordinator.async_set_onoff(self._uid, True)

        # Update state immediately
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        await self.coordinator.async_set_onoff(self._uid, False)
        # Update state immediately
        await self.coordinator.async_request_refresh()

    async def async_update(self) -> None:
        """Update the light state."""
        # Get current state
        is_on = await self.coordinator.async_get_onoff(self._uid)
        level = await self.coordinator.async_get_level(self._uid)

        # Update device in coordinator
        device = self.coordinator.get_device(self._uid)
        if device:
            if is_on is not None:
                device["is_on"] = is_on
            if level is not None:
                device["level"] = level

        self.async_write_ha_state()
