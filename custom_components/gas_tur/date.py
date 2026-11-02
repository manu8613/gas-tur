"""Date of the last bill reading."""

from __future__ import annotations

from datetime import date

from homeassistant.components.date import DateEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import KEY_BILL_DATE
from .entity import GasTurEntity
from .manager import GasTurConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GasTurConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([GasTurBillDate(entry.runtime_data, "fecha_factura")])


class GasTurBillDate(GasTurEntity, DateEntity):
    """Date of the reading on the last bill."""

    _attr_entity_category = EntityCategory.CONFIG

    @property
    def native_value(self) -> date:
        return self.coordinator.bill_date

    async def async_set_value(self, value: date) -> None:
        self.coordinator.async_set_setting(KEY_BILL_DATE, value.isoformat())
