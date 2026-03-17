"""The Levven integration."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_START, Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import async_get as async_get_device_registry

from .const import (
    CONFIGURABLE_RECEIVER_TYPES,
    DOMAIN,
    ENTITY_TYPE_LIGHT,
    ENTITY_TYPE_SWITCH,
)
from .coordinator import LevvenDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.LIGHT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Levven integration domain. Register brand static path so the icon can be served."""

    @callback
    def _register_brand(_):
        brand_path = Path(__file__).parent / "brand"
        if not brand_path.is_dir() or not getattr(hass, "http", None):
            return
        hass.create_task(
            hass.http.async_register_static_paths(
                [StaticPathConfig("/api/levven_brand", str(brand_path), cache_headers=True)]
            )
        )

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, _register_brand)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Levven from a config entry."""
    # Create coordinator
    coordinator = LevvenDataUpdateCoordinator(hass, entry)

    # Store coordinator in hass data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}

    # Set up coordinator
    await coordinator.async_setup()

    # Create gateway device so entities can use via_device (avoids "non existing via_device" warning)
    if coordinator.gwid and coordinator.gwid != "unknown":
        dev_reg = async_get_device_registry(hass)
        dev_reg.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, coordinator.gwid)},
            manufacturer="Levven",
            name=coordinator.gateway_name or f"Levven Gateway {coordinator.gwid}",
        )

    # Forward the setup to the platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register service for configuring entity type
    if not hass.services.has_service(DOMAIN, "set_entity_type"):
        hass.services.async_register(
            DOMAIN,
            "set_entity_type",
            async_handle_set_entity_type,
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Stop coordinator (mDNS browser) and remove from hass data
    if unload_ok and entry.entry_id in hass.data.get(DOMAIN, {}):
        coordinator = hass.data[DOMAIN][entry.entry_id].get("coordinator")
        if coordinator:
            coordinator.async_stop()
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


@callback
async def async_handle_set_entity_type(call: ServiceCall) -> None:
    """Handle set_entity_type service call."""
    entity_id = call.data.get("entity_id")
    entity_type = call.data.get("entity_type")

    if entity_type not in (ENTITY_TYPE_LIGHT, ENTITY_TYPE_SWITCH):
        _LOGGER.error("Invalid entity_type: %s. Must be 'light' or 'switch'", entity_type)
        return

    entity_registry = er.async_get(call.hass)
    entity_entry = entity_registry.async_get(entity_id)

    if not entity_entry:
        _LOGGER.error("Entity %s not found", entity_id)
        return

    if entity_entry.platform != DOMAIN:
        _LOGGER.error("Entity %s is not a Levven entity", entity_id)
        return

    # Extract UID from unique_id (format: levven_{gwid}_{uid})
    parts = entity_entry.unique_id.split("_")
    if len(parts) < 3:
        _LOGGER.error("Invalid unique_id format: %s", entity_entry.unique_id)
        return

    uid = "_".join(parts[2:])

    # Check if this is a configurable device
    coordinator = None
    for entry_id, data in call.hass.data.get(DOMAIN, {}).items():
        coordinator = data.get("coordinator")
        if coordinator:
            device = coordinator.get_device(uid)
            if device and device.get("type") in CONFIGURABLE_RECEIVER_TYPES:
                break
        coordinator = None

    if not coordinator:
        _LOGGER.error("Device %s is not a configurable device type", entity_id)
        return

    # Update entity options
    current_options = dict(entity_entry.options or {})
    current_options.setdefault(DOMAIN, {})["entity_type"] = entity_type
    entity_registry.async_update_entity_options(
        entity_id, DOMAIN, current_options[DOMAIN]
    )

    # Update device in coordinator
    device = coordinator.get_device(uid)
    if device:
        device["entity_type"] = entity_type

    _LOGGER.info(
        "Set entity type for %s to %s. Reload the integration for changes to take effect.",
        entity_id,
        entity_type,
    )
