"""Sensors for Gas TUR."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfVolume, UnitOfVolumeFlowRate
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from .const import TARIFF_URLS
from .entity import GasTurEntity
from .manager import GasTurConfigEntry, GasTurManager
from .tariff import daily_fixed, quarter_start

EUR = "EUR"


def _next_revision(manager: GasTurManager) -> str:
    today = dt_util.now().date()
    start = quarter_start(today)
    month = start.month + 3
    year = start.year + (1 if month > 12 else 0)
    month = month - 12 if month > 12 else month
    return start.replace(year=year, month=month).isoformat()


def _price_attrs(manager: GasTurManager) -> dict[str, Any]:
    price = manager.price
    return {
        "tarifa": f"TUR {manager.tariff[-1]}",
        "vigente_desde": price.start.isoformat() if price else None,
        "termino_fijo_mes": price.fixed_month if price else None,
        "termino_fijo_dia": daily_fixed(price.fixed_month) if price else None,
        "impuesto_hidrocarburos": manager.ieh,
        "iva": manager.vat,
        "factor_conversion": manager.factor,
        "alquiler_contador_dia": manager.rental,
        "historial": [p.as_dict() for p in reversed(manager.prices)],
        "proxima_revision": _next_revision(manager),
    }


def _bill_attrs(manager: GasTurManager) -> dict[str, Any]:
    bill = manager.bill
    return bill.as_attributes() if bill else {}


def _status(manager: GasTurManager) -> str:
    if not manager.auto_prices:
        return "manual"
    if manager.price_error:
        return "error"
    return "ok" if manager.prices else "pendiente"


@dataclass(frozen=True, kw_only=True)
class GasTurSensorDescription(SensorEntityDescription):
    """Describes a Gas TUR sensor."""

    value_fn: Callable[[GasTurManager], StateType | datetime]
    attr_fn: Callable[[GasTurManager], dict[str, Any]] | None = None


SENSORS: tuple[GasTurSensorDescription, ...] = (
    GasTurSensorDescription(
        key="lectura",
        device_class=SensorDeviceClass.GAS,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda m: m.reading,
    ),
    GasTurSensorDescription(
        key="consumo_hoy",
        device_class=SensorDeviceClass.GAS,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda m: m.m3_today,
    ),
    GasTurSensorDescription(
        key="consumo_mes",
        device_class=SensorDeviceClass.GAS,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda m: m.m3_month,
    ),
    GasTurSensorDescription(
        key="consumo_factura",
        device_class=SensorDeviceClass.GAS,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda m: m.m3_since_bill,
    ),
    GasTurSensorDescription(
        key="caudal",
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda m: m.flow,
    ),
    GasTurSensorDescription(
        key="ultimo_pulso",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda m: m.last_pulse,
    ),
    GasTurSensorDescription(
        key="precio_kwh",
        native_unit_of_measurement=f"{EUR}/kWh",
        suggested_display_precision=6,
        value_fn=lambda m: m.price.variable if m.price else None,
        attr_fn=_price_attrs,
    ),
    GasTurSensorDescription(
        key="termino_fijo",
        native_unit_of_measurement=f"{EUR}/mes",
        suggested_display_precision=2,
        value_fn=lambda m: m.price.fixed_month if m.price else None,
    ),
    GasTurSensorDescription(
        key="precio_m3",
        native_unit_of_measurement=f"{EUR}/{UnitOfVolume.CUBIC_METERS}",
        suggested_display_precision=4,
        value_fn=lambda m: m.price_m3,
    ),
    GasTurSensorDescription(
        key="fijo_dia",
        native_unit_of_measurement=f"{EUR}/d",
        suggested_display_precision=4,
        value_fn=lambda m: m.fixed_day,
    ),
    GasTurSensorDescription(
        key="coste_hoy",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=EUR,
        suggested_display_precision=2,
        value_fn=lambda m: m.cost_today,
    ),
    GasTurSensorDescription(
        key="coste_mes",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=EUR,
        suggested_display_precision=2,
        value_fn=lambda m: m.cost_month,
    ),
    GasTurSensorDescription(
        key="factura",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=EUR,
        suggested_display_precision=2,
        value_fn=lambda m: m.bill.total if m.bill else None,
        attr_fn=_bill_attrs,
    ),
    GasTurSensorDescription(
        key="prevision_factura",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=EUR,
        suggested_display_precision=2,
        value_fn=lambda m: m.bill.forecast if m.bill else None,
    ),
    GasTurSensorDescription(
        key="estado_precios",
        device_class=SensorDeviceClass.ENUM,
        options=["ok", "error", "manual", "pendiente"],
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_status,
        attr_fn=lambda m: {
            "url": TARIFF_URLS[m.tariff],
            "ultima_comprobacion": m.price_checked.isoformat() if m.price_checked else None,
            "error": m.price_error,
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GasTurConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    manager = entry.runtime_data
    async_add_entities(GasTurSensor(manager, description) for description in SENSORS)


class GasTurSensor(GasTurEntity, SensorEntity):
    """A Gas TUR sensor."""

    entity_description: GasTurSensorDescription
    _unrecorded_attributes = frozenset({"historial", "proxima_revision", "lineas"})

    def __init__(self, manager: GasTurManager, description: GasTurSensorDescription) -> None:
        super().__init__(manager, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType | datetime:
        return self.entity_description.value_fn(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attr_fn is None:
            return None
        return self.entity_description.attr_fn(self.coordinator)
