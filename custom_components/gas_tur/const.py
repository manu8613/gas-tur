"""Constants for Gas TUR."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "gas_tur"

CONF_PULSE_ENTITY: Final = "pulse_entity"
CONF_EDGE: Final = "edge"
CONF_M3_PER_PULSE: Final = "m3_per_pulse"
CONF_INITIAL_READING: Final = "initial_reading"
CONF_TARIFF: Final = "tariff"
CONF_CREATE_DASHBOARD: Final = "create_dashboard"
CONF_DEBOUNCE: Final = "debounce"
CONF_AUTO_PRICES: Final = "auto_prices"
CONF_PERIOD_DAYS: Final = "period_days"
CONF_BILL_DATE: Final = "bill_date"
CONF_BILL_READING: Final = "bill_reading"
CONF_FACTOR: Final = "factor"
CONF_RENTAL: Final = "rental"

EDGE_ON_OFF: Final = "on_off"
EDGE_OFF_ON: Final = "off_on"

TARIFF_URLS: Final = {
    "tur1": "https://www.comercializadoraregulada.es/regulada/gas/tur_1",
    "tur2": "https://www.comercializadoraregulada.es/regulada/gas/tur_2",
    "tur3": "https://www.comercializadoraregulada.es/regulada/gas/tur_3",
}

DEFAULT_NAME: Final = "Gas"
DEFAULT_M3_PER_PULSE: Final = 0.01
DEFAULT_TARIFF: Final = "tur2"
DEFAULT_FACTOR: Final = 10.5
DEFAULT_IEH: Final = 0.00234
DEFAULT_VAT: Final = 21.0
DEFAULT_RENTAL: Final = 0.019068
DEFAULT_DEBOUNCE: Final = 1.0
DEFAULT_PERIOD_DAYS: Final = 61

PRICE_REFRESH: Final = timedelta(hours=6)
TICK: Final = timedelta(seconds=30)
FLOW_TIMEOUT: Final = timedelta(minutes=15)
MAX_FLOW: Final = 40.0  # m³/h, above any domestic meter (G4 = 6 m³/h)

STORAGE_VERSION: Final = 1

DASHBOARD_URL: Final = "gas-tur"

# Keys of the values the user edits from the dashboard (number/date entities).
KEY_FACTOR: Final = "factor"
KEY_IEH: Final = "ieh"
KEY_RENTAL: Final = "rental"
KEY_VAT: Final = "vat"
KEY_BILL_READING: Final = "bill_reading"
KEY_BILL_DATE: Final = "bill_date"
KEY_READING: Final = "reading"

SERVICE_NEW_BILL: Final = "nueva_factura"
SERVICE_SET_READING: Final = "ajustar_lectura"
SERVICE_SET_PRICE: Final = "establecer_precio"
SERVICE_REFRESH_PRICES: Final = "actualizar_precios"
SERVICE_CREATE_DASHBOARD: Final = "crear_panel"

ATTR_CONFIG_ENTRY: Final = "config_entry_id"
ATTR_DATE: Final = "fecha"
ATTR_READING: Final = "lectura"
ATTR_FACTOR: Final = "factor_conversion"
ATTR_FIXED: Final = "termino_fijo"
ATTR_VARIABLE: Final = "termino_variable"
