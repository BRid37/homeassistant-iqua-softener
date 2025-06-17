import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]  # If you add other platforms, just add to this list

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool:
    """Set up iQua Softener from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass_data = dict(entry.data)
    unsub_options_update_listener = entry.add_update_listener(options_update_listener)
    hass_data["unsub_options_update_listener"] = unsub_options_update_listener
    hass.data[DOMAIN][entry.entry_id] = hass_data

    # Modern pattern: async_forward_entry_setups (plural, for multi-platform support)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def options_update_listener(
    hass: HomeAssistant, config_entry: ConfigEntry
):
    """Reload if options are updated."""
    await hass.config_entries.async_reload(config_entry.entry_id)

async def async_unload_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool:
    """Unload iQua Softener config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Defensive: Only unsubscribe if key exists (prevents KeyError)
    hass_data = hass.data[DOMAIN].get(entry.entry_id)
    if hass_data and "unsub_options_update_listener" in hass_data:
        hass_data["unsub_options_update_listener"]()
    # Remove entry from domain data if unloaded
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
