"""Tests for the pure tariff logic (no Home Assistant needed)."""

from __future__ import annotations

from datetime import date
import importlib.util
from pathlib import Path
import sys
import unittest

_SPEC = importlib.util.spec_from_file_location(
    "gas_tur_tariff",
    Path(__file__).parents[1] / "custom_components" / "gas_tur" / "tariff.py",
)
tariff = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = tariff
_SPEC.loader.exec_module(tariff)

PAGE = """
<div><h3>TUR 2</h3><p><strong>Precios sin descuentos ni impuestos:</strong></p>
<ul><li>T&eacute;rmino fijo: 8,17&nbsp;&euro;/mes</li><li>Término variable: <b>0,050428</b> €/kWh</li></ul>
<p><strong>Precios incluyendo impuestos (impuesto hidrocarburos e IVA 21%):</strong></p>
<ul><li>Término fijo: 9,89 €/mes</li><li>Término variable: 0,063849 €/kWh</li></ul></div>
"""

HISTORY = [
    tariff.PricePeriod(date(2026, 7, 1), 8.11, 0.041199),
    tariff.PricePeriod(date(2026, 10, 1), 8.17, 0.050428),
]


class ParseTest(unittest.TestCase):
    def test_parse_page(self):
        prices = tariff.parse_prices(PAGE)
        self.assertEqual(prices.fixed_month, 8.17)
        self.assertEqual(prices.variable, 0.050428)
        self.assertEqual(prices.fixed_month_taxed, 9.89)
        self.assertEqual(prices.variable_taxed, 0.063849)

    def test_derive_ieh(self):
        self.assertEqual(tariff.derive_ieh(tariff.parse_prices(PAGE), 21), 0.00234)

    def test_parse_rejects_garbage(self):
        with self.assertRaises(ValueError):
            tariff.parse_prices("<html>mantenimiento</html>")
        with self.assertRaises(ValueError):
            tariff.parse_prices("Término fijo: 0 €/mes Término variable: 0 €/kWh")

    def test_daily_fixed_matches_bill(self):
        self.assertEqual(tariff.daily_fixed(8.11), 0.26663)
        self.assertEqual(tariff.daily_fixed(8.17), 0.268603)


class DatesTest(unittest.TestCase):
    def test_effective_date(self):
        self.assertEqual(tariff.effective_date(date(2026, 10, 2)), date(2026, 10, 1))
        self.assertEqual(tariff.effective_date(date(2026, 12, 31)), date(2026, 12, 31))
        self.assertEqual(tariff.effective_date(date(2027, 1, 15)), date(2027, 1, 1))

    def test_price_on(self):
        self.assertEqual(tariff.price_on(HISTORY, date(2026, 9, 30)).variable, 0.041199)
        self.assertEqual(tariff.price_on(HISTORY, date(2026, 10, 1)).variable, 0.050428)
        self.assertEqual(tariff.price_on(HISTORY, date(2026, 1, 1)).variable, 0.041199)


class BillTest(unittest.TestCase):
    """The bill of 21/10/2026: 24/08 → 21/10, 37 m³, 10,318 kWh/m³, 41,77 €."""

    def bill(self, **kwargs):
        args = dict(
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
        args.update(kwargs)
        return tariff.compute_bill(**args)

    def test_october_bill_to_the_cent(self):
        bill = self.bill()
        self.assertEqual((bill.days, bill.m3, bill.kwh), (58, 37, 382))
        amounts = [(line.concept, line.quantity, line.amount) for line in bill.lines]
        self.assertEqual(
            amounts,
            [
                ("Término fijo", 37, 9.87),
                ("Término fijo", 21, 5.64),
                ("Consumo gas", 244, 10.05),
                ("Consumo gas", 138, 6.96),
                ("Impuesto hidrocarburos", 382, 0.89),
                ("Alquiler de contador", 58, 1.11),
            ],
        )
        self.assertEqual(bill.lines[0].start, date(2026, 8, 25))
        self.assertEqual(bill.lines[0].end, date(2026, 9, 30))
        self.assertEqual(bill.lines[1].start, date(2026, 10, 1))
        self.assertEqual((bill.base, bill.vat, bill.total), (34.52, 7.25, 41.77))

    def test_same_day_is_empty(self):
        bill = self.bill(last_reading_date=date(2026, 10, 21), last_reading=22814)
        self.assertEqual((bill.days, bill.total, bill.lines), (0, 0.0, []))

    def test_single_price(self):
        bill = self.bill(last_reading_date=date(2026, 10, 21), last_reading=22814,
                         end_date=date(2026, 11, 2), current_reading=22830.2)
        self.assertEqual((bill.days, bill.m3, bill.kwh), (12, 16, 165))
        self.assertEqual(len(bill.lines), 4)
        self.assertEqual(bill.lines[0].amount, 3.22)

    def test_reading_below_bill_gives_zero(self):
        self.assertEqual(self.bill(current_reading=22700).m3, 0)


class PriceTest(unittest.TestCase):
    def test_price_per_m3(self):
        self.assertEqual(tariff.price_per_m3(0.050428, 0.00234, 10.462, 21), 0.668)

    def test_fixed_per_day(self):
        self.assertAlmostEqual(tariff.fixed_per_day_taxed(8.17, 0.019068, 21), 0.348082, places=6)

    def test_add_price_replaces_same_start(self):
        hist = tariff.add_price(HISTORY, tariff.PricePeriod(date(2026, 10, 1), 8.17, 0.05))
        self.assertEqual([p.variable for p in hist], [0.041199, 0.05])


if __name__ == "__main__":
    unittest.main()
