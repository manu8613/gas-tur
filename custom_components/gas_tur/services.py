"""Actions (services) for Gas TUR."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
import homeassistant.helpers.config_validation as cv

from .compat import vol
from .const import (
    ATTR_CONFIG_ENTRY,
    ATTR_DATE,
    ATTR_FACTOR,
    ATTR_FIXED,
    ATTR_READING,
    ATTR_VARIABLE,
    DOMAIN,
    SERVICE_CREATE_DASHBOARD,
    SERVICE_NEW_BILL,
    SERVICE_REFRESH_PRICES,
    SERVICE_SET_PRICE,
    SERVICE_SET_READING,
)
from .manager import GasTurConfigEntry

_ENTRY = {vol.Optional(ATTR_CONFIG_ENTRY): cv.string}

SCHEMAS = {
    SERVICE_NEW_BILL: vol.Schema(
        {
            **_ENTRY,
            vol.Required(ATTR_DATE): cv.date,
            vol.Required(ATTR_READING): vol.All(vol.Coerce(float), vol.Range(min=0)),
            vol.Optional(ATTR_FACTOR): vol.All(vol.Coerce(float), vol.Range(min=5, max=15)),
        }
    ),
    SERVICE_SET_READING: vol.Schema(
        {**_ENTRY, vol.Required(ATTR_READING): vol.All(vol.Coerce(float), vol.Range(min=0))}
    ),
    SERVICE_SET_PRICE: vol.Schema(
        {
            **_ENTRY,
            vol.Required(ATTR_DATE): cv.date,
            vol.Required(ATTR_FIXED): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
            vol.Required(ATTR_VARIABLE): vol.All(vol.Coerce(float), vol.Range(min=0, max=1)),
        }
    ),
    SERVICE_REFRESH_PRICES: vol.Schema(_ENTRY),
    SERVICE_CREATE_DASHBOARD: vol.Schema(_ENTRY),
}


def _entry(hass: HomeAssistant, call: ServiceCall) -> GasTurConfigEntry:
    entries = [
        e for e in hass.config_entries.async_entries(DOMAIN) if e.state is ConfigEntryState.LOADED
    ]
    if entry_id := call.data.get(ATTR_CONFIG_ENTRY):
        entries = [e for e in entries if e.entry_id == entry_id]
    if len(entries) != 1:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_entry" if not entries else "several_entries",
        )
    return entries[0]


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the actions once for the whole integration."""

    async def new_bill(call: ServiceCall) -> None:
        manager = _entry(hass, call).runtime_data
        manager.async_new_bill(call.data[ATTR_DATE], call.data[ATTR_READING], call.data.get(ATTR_FACTOR))

    async def set_reading(call: ServiceCall) -> None:
        _entry(hass, call).runtime_data.async_set_reading(call.data[ATTR_READING])

    async def set_price(call: ServiceCall) -> None:
        _entry(hass, call).runtime_data.async_set_price(
            call.data[ATTR_DATE], call.data[ATTR_FIXED], call.data[ATTR_VARIABLE]
        )

    async def refresh_prices(call: ServiceCall) -> None:
        manager = _entry(hass, call).runtime_data
        await manager.async_refresh()

    async def create_dashboard(call: ServiceCall) -> None:
        from .dashboard import async_setup_dashboard

        await async_setup_dashboard(hass, _entry(hass, call))

    handlers = {
        SERVICE_NEW_BILL: new_bill,
        SERVICE_SET_READING: set_reading,
        SERVICE_SET_PRICE: set_price,
        SERVICE_REFRESH_PRICES: refresh_prices,
        SERVICE_CREATE_DASHBOARD: create_dashboard,
    }
    for name, handler in handlers.items():
        hass.services.async_register(DOMAIN, name, handler, schema=SCHEMAS[name])
