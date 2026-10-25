"""The SYR Local integration (read-only)."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SyrLocalClient
from .coordinator import SyrLocalConfigEntry, SyrLocalCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: SyrLocalConfigEntry) -> bool:
    """Set up SYR Local from a config entry."""
    client = SyrLocalClient(
        async_get_clientsession(hass), entry.data[CONF_HOST], entry.data[CONF_PORT]
    )
    coordinator = SyrLocalCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SyrLocalConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
