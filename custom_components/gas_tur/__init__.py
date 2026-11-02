"""Gas TUR: gas meter pulses, regulated TUR prices and bill estimate."""

from __future__ import annotations

import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .const import CONF_CREATE_DASHBOARD, DOMAIN, STORAGE_VERSION
from .dashboard import async_remove_dashboard, async_setup_dashboard
from .manager import GasTurConfigEntry, GasTurManager
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER, Platform.DATE]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: GasTurConfigEntry) -> bool:
    manager = GasTurManager(hass, entry)
    await manager.async_load()
    await manager.async_config_entry_first_refresh()
    entry.runtime_data = manager
    manager.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))

    if entry.options.get(CONF_CREATE_DASHBOARD, entry.data.get(CONF_CREATE_DASHBOARD, True)):
        await async_setup_dashboard(hass, entry)
    return True


async def _async_reload(hass: HomeAssistant, entry: GasTurConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: GasTurConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_flush()
        async_remove_dashboard(hass, entry)
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: GasTurConfigEntry) -> None:
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()
    await hass.async_add_executor_job(_remove_panel_file, hass, entry.entry_id)


def _remove_panel_file(hass: HomeAssistant, entry_id: str) -> None:
    from .dashboard import panel_path

    path = panel_path(hass, entry_id)
    if path.exists():
        path.unlink()
