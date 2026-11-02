"""Editable values for Gas TUR (bill settings and reading adjustment)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import KEY_BILL_READING, KEY_FACTOR, KEY_IEH, KEY_RENTAL, KEY_VAT
from .entity import GasTurEntity
from .manager import GasTurConfigEntry, GasTurManager


@dataclass(frozen=True, kw_only=True)
class GasTurNumberDescription(NumberEntityDescription):
    """Describes a Gas TUR number."""

    setting: str | None = None
    value_fn: Callable[[GasTurManager], float] | None = None
    set_fn: Callable[[GasTurManager, float], None] | None = None


NUMBERS: tuple[GasTurNumberDescription, ...] = (
    GasTurNumberDescription(
        key="factor_conversion",
        setting=KEY_FACTOR,
        native_min_value=5,
        native_max_value=15,
        native_step=0.001,
        native_unit_of_measurement="kWh/m³",
    ),
    GasTurNumberDescription(
        key="lectura_factura",
        setting=KEY_BILL_READING,
        native_min_value=0,
        native_max_value=9_999_999,
        native_step=0.01,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
    ),
    GasTurNumberDescription(
        key="impuesto_hidrocarburos",
        setting=KEY_IEH,
        native_min_value=0,
        native_max_value=0.05,
        native_step=0.000001,
        native_unit_of_measurement="EUR/kWh",
    ),
    GasTurNumberDescription(
        key="alquiler_contador",
        setting=KEY_RENTAL,
        native_min_value=0,
        native_max_value=2,
        native_step=0.000001,
        native_unit_of_measurement="EUR/d",
    ),
    GasTurNumberDescription(
        key="iva",
        setting=KEY_VAT,
        native_min_value=0,
        native_max_value=30,
        native_step=0.1,
        native_unit_of_measurement=PERCENTAGE,
    ),
    GasTurNumberDescription(
        key="ajuste_lectura",
        native_min_value=0,
        native_max_value=9_999_999,
        native_step=0.01,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        value_fn=lambda m: m.reading,
        set_fn=lambda m, value: m.async_set_reading(value),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GasTurConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    manager = entry.runtime_data
    async_add_entities(GasTurNumber(manager, description) for description in NUMBERS)


class GasTurNumber(GasTurEntity, NumberEntity):
    """A value the user can edit from the dashboard."""

    entity_description: GasTurNumberDescription
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, manager: GasTurManager, description: GasTurNumberDescription) -> None:
        super().__init__(manager, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float:
        description = self.entity_description
        if description.value_fn is not None:
            return description.value_fn(self.coordinator)
        return float(self.coordinator.settings[description.setting])

    async def async_set_native_value(self, value: float) -> None:
        description = self.entity_description
        if description.set_fn is not None:
            description.set_fn(self.coordinator, value)
        else:
            self.coordinator.async_set_setting(description.setting, float(value))
