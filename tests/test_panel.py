"""Render the dashboard templates with realistic states (no Home Assistant needed)."""

from __future__ import annotations

from datetime import date, datetime
import importlib.util
from pathlib import Path
import sys
import unittest

import jinja2
import yaml

_BASE = Path(__file__).parents[1] / "custom_components" / "gas_tur"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"gas_tur_{name}", _BASE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tariff = _load("tariff")
panel = _load("panel")

IDS = {key: f"{platform}.gas_{key}" for key, platform in panel.ENTITY_KEYS.items()}
HISTORY = [
    tariff.PricePeriod(date(2026, 7, 1), 8.11, 0.041199),
    tariff.PricePeriod(date(2026, 10, 1), 8.17, 0.050428),
]


def _states(bill_attrs):
    states = {
        IDS["coste_hoy"]: ("0.41", {}),
        IDS["consumo_hoy"]: ("0.09", {}),
        IDS["coste_mes"]: ("12.3", {}),
        IDS["consumo_mes"]: ("14.2", {}),
        IDS["factor_conversion"]: ("10.318", {}),
        IDS["precio_m3"]: ("0.6588", {}),
        IDS["fijo_dia"]: ("0.348082", {}),
        IDS["impuesto_hidrocarburos"]: ("0.00234", {}),
        IDS["iva"]: ("21.0", {}),
        IDS["estado_precios"]: ("ok", {"error": None}),
        IDS["precio_kwh"]: (
            "0.050428",
            {
                "tarifa": "TUR2",
                "vigente_desde": "2026-10-01",
                "termino_fijo_mes": 8.17,
                "historial": [p.as_dict() for p in reversed(HISTORY)],
                "proxima_revision": "2027-01-01",
            },
        ),
        IDS["factura"]: (str(bill_attrs.get("total", "unknown")), bill_attrs),
    }
    return states


def _env(states):
    env = jinja2.Environment()
    env.globals["states"] = lambda e: states.get(e, ("unknown", {}))[0]
    env.globals["state_attr"] = lambda e, a: states.get(e, ("", {}))[1].get(a)
    env.globals["now"] = lambda: datetime(2026, 10, 21, 20, 0)
    return env


def _templates(config):
    found = []

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("content",) and isinstance(value, str) and "{" in value:
                    found.append(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(config)
    return found


class PanelTest(unittest.TestCase):
    def setUp(self):
        self.bill = tariff.compute_bill(
            last_reading_date=date(2026, 8, 24),
            last_reading=22777,
            end_date=date(2026, 10, 21),
            current_reading=22814.45,
            factor=10.318,
            history=HISTORY,
            ieh=0.00234,
            rental_day=0.019068,
            vat=21,
        )
        self.config = panel.build_panel(IDS, "Gas")

    def test_yaml_roundtrip_and_no_placeholders(self):
        text = yaml.safe_dump(self.config, allow_unicode=True, sort_keys=False)
        self.assertEqual(yaml.safe_load(text), self.config)
        self.assertNotRegex(text, r"@(lectura|factura|precio|consumo|coste|iva|caudal)")

    def test_all_templates_render(self):
        env = _env(_states(self.bill.as_attributes()))
        for template in _templates(self.config):
            env.from_string(template).render()

    def test_bill_table(self):
        env = _env(_states(self.bill.as_attributes()))
        bill_tpl = next(t for t in _templates(self.config) if "lineas" in t)
        out = env.from_string(bill_tpl).render()
        self.assertIn("Desde el **24/08/2026** · 58 días · **37 m³** → 382 kWh", out)
        self.assertIn("| Término fijo<br><sub>25/08/2026 – 30/09/2026</sub> | 37 días × 0,266630 €/día | 9,87 € |", out)
        self.assertIn("| Consumo gas<br><sub>01/10/2026 – 21/10/2026</sub> | 138 kWh × 0,050428 €/kWh | 6,96 € |", out)
        self.assertIn("| **Total hasta hoy** | | **41,77 €** |", out)
        rows = [line for line in out.splitlines() if line.startswith("|")]
        self.assertEqual(len(rows), 2 + 6 + 3)

    def test_bill_just_closed(self):
        closed = tariff.compute_bill(
            last_reading_date=date(2026, 10, 21), last_reading=22814, end_date=date(2026, 10, 21),
            current_reading=22814.45, factor=10.318, history=HISTORY, ieh=0.00234, rental_day=0.019068, vat=21,
        )
        env = _env(_states(closed.as_attributes()))
        bill_tpl = next(t for t in _templates(self.config) if "lineas" in t)
        self.assertIn("Factura recién cerrada el **21/10/2026**", env.from_string(bill_tpl).render())

    def test_prices_table(self):
        env = _env(_states(self.bill.as_attributes()))
        tpl = next(t for t in _templates(self.config) if "Sin impuestos" in t)
        out = env.from_string(tpl).render()
        self.assertIn("| Energía | 0,050428 €/kWh | 0,063849 €/kWh |", out)
        self.assertIn("| 01/07/2026 | 8,11 €/mes | 0,041199 €/kWh |", out)
        self.assertIn("Próxima revisión: **01/01/2027**", out)

    def test_today_card(self):
        env = _env(_states(self.bill.as_attributes()))
        tpl = next(t for t in _templates(self.config) if "Gasto de hoy" in t)
        out = env.from_string(tpl).render()
        self.assertIn("# 0,41 €", out)
        self.assertIn("media **0,59 €/día**", out)


if __name__ == "__main__":
    unittest.main()
