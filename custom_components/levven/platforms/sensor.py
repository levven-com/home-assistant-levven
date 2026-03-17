"""Sensor platform for Levven transmitters (wall switches) — tri-state: idle, up, down."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import DEVICE_TYPE_TO_MODEL, DOMAIN
from ..coordinator import LevvenDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


@callback
def _register_transmitter_listener(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    coordinator: LevvenDataUpdateCoordinator,
) -> None:
    """Register a listener so we add entities when new transmitters appear from MQTT."""

    added_uids: set[str] = set()

    @callback
    def _add_new_transmitters() -> None:
        # Only add entities if the config entry is still registered (avoids "unknown config entry" when entry was removed or race at startup)
        if hass.config_entries.async_get_entry(config_entry.entry_id) is None:
            return
        devices = coordinator.get_devices_by_type("transmitter")
        entity_reg = er.async_get(hass)
        new_entities = []
        for device in devices:
            uid = device["uid"]
            if uid in added_uids:
                continue
            unique_id = f"levven_{coordinator.gwid}_tx_{uid}"
            if entity_reg.async_get_entity_id("sensor", DOMAIN, unique_id):
                added_uids.add(uid)
                continue
            added_uids.add(uid)
            new_entities.append(LevvenTransmitterSensor(coordinator, device))
        if new_entities:
            async_add_entities(new_entities)

    # Add any transmitters already in coordinator (e.g. from reload)
    _add_new_transmitters()
    coordinator.async_add_listener(_add_new_transmitters)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Levven transmitter sensors (tri-state: idle / up / down). New transmitters added when seen via MQTT."""
    coordinator: LevvenDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]["coordinator"]

    if not coordinator._include_transmitters:
        return

    _register_transmitter_listener(hass, config_entry, async_add_entities, coordinator)


class LevvenTransmitterSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Levven transmitter (wall switch) as a tri-state sensor.

    States: idle (nothing pressed), up (top pressed), down (bottom pressed).
    Up/down are momentary and revert to idle after a short delay.
    Future: long_up / long_down when Levven exposes long-press in the API.
    """

    _attr_native_value = "idle"

    def __init__(
        self,
        coordinator: LevvenDataUpdateCoordinator,
        device: dict[str, Any],
    ) -> None:
        """Initialize the transmitter sensor."""
        super().__init__(coordinator)
        self._uid = device["uid"]
        self._device = device
        self._attr_unique_id = f"levven_{coordinator.gwid}_tx_{device['uid']}"
        self._attr_name = device.get("name", f"Levven Transmitter {device['uid']}")

        device_type = device.get("type", 0)
        model = DEVICE_TYPE_TO_MODEL.get(device_type, f"Type {device_type}")
        device_info_kw: dict[str, Any] = {
            "identifiers": {(DOMAIN, f"{coordinator.gwid}_tx_{device['uid']}")},
            "name": device.get("name", f"Levven Transmitter {device['uid']}"),
            "manufacturer": "Levven",
            "model": model,
        }
        if coordinator.gwid and coordinator.gwid != "unknown":
            device_info_kw["via_device"] = (DOMAIN, coordinator.gwid)
        self._attr_device_info = DeviceInfo(**device_info_kw)

    @property
    def native_value(self) -> str:
        """Return current state: idle, up, or down (future: long_up, long_down)."""
        return self.coordinator.get_transmitter_state(self._uid)

    @property
    def available(self) -> bool:
        """Available when gateway is seen."""
        return self.coordinator.gateway_available
