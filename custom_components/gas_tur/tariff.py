"""Pure tariff and bill logic for Gas TUR (no Home Assistant imports)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
import html
import re
from typing import Any

_FIXED_RE = re.compile(r"T[ée]rmino\s+fijo\s*:?\s*([0-9]+(?:[.,][0-9]+)?)\s*€\s*/\s*mes", re.I)
_VARIABLE_RE = re.compile(
    r"T[ée]rmino\s+variable\s*:?\s*([0-9]+(?:[.,][0-9]+)?)\s*€\s*/\s*kWh", re.I
)
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


def money(value: float) -> float:
    """Round to cents, half up, like the bill."""
    return float(Decimal(repr(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def round_int(value: float) -> int:
    """Round to the nearest integer, half up."""
    return int(Decimal(repr(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _num(text: str) -> float:
    return float(text.replace(".", "").replace(",", ".")) if "," in text else float(text)


@dataclass(frozen=True)
class ParsedPrices:
    """Prices read from the regulated retailer page."""

    fixed_month: float
    variable: float
    fixed_month_taxed: float | None = None
    variable_taxed: float | None = None


def parse_prices(page: str) -> ParsedPrices:
    """Parse the TUR page. First match = without taxes, second = with taxes."""
    text = _SPACE_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", page)))
    fixed = [_num(m) for m in _FIXED_RE.findall(text)]
    variable = [_num(m) for m in _VARIABLE_RE.findall(text)]
    if not fixed or not variable:
        raise ValueError("No se encuentran los precios en la página")
    if not 0.5 < fixed[0] < 100 or not 0.005 < variable[0] < 1:
        raise ValueError(f"Precios fuera de rango: {fixed[0]} €/mes, {variable[0]} €/kWh")
    return ParsedPrices(
        fixed_month=fixed[0],
        variable=variable[0],
        fixed_month_taxed=fixed[1] if len(fixed) > 1 else None,
        variable_taxed=variable[1] if len(variable) > 1 else None,
    )


def derive_ieh(prices: ParsedPrices, vat: float) -> float | None:
    """Hydrocarbon tax implied by the taxed and untaxed variable prices."""
    if prices.variable_taxed is None:
        return None
    ieh = round(prices.variable_taxed / (1 + vat / 100) - prices.variable, 6)
    return ieh if 0 <= ieh < 0.02 else None


def daily_fixed(fixed_month: float) -> float:
    """€/month to €/day as the bill does it (×12/365, 6 decimals)."""
    return round(fixed_month * 12 / 365, 6)


def quarter_start(day: date) -> date:
    """First day of the quarter (TUR revisions: 1 Jan, Apr, Jul, Oct)."""
    return date(day.year, 3 * ((day.month - 1) // 3) + 1, 1)


def effective_date(today: date) -> date:
    """Date a newly detected price applies from.

    TUR revisions take effect on the first day of a quarter and are published
    a day or two before; a change seen early in a quarter dates from its start.
    """
    start = quarter_start(today)
    return start if (today - start).days <= 20 else today


@dataclass(frozen=True)
class PricePeriod:
    """A price in force from ``start`` onwards."""

    start: date
    fixed_month: float
    variable: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "start": self.start.isoformat(),
            "fixed_month": self.fixed_month,
            "variable": self.variable,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PricePeriod:
        return cls(date.fromisoformat(data["start"]), float(data["fixed_month"]), float(data["variable"]))


def add_price(history: list[PricePeriod], period: PricePeriod) -> list[PricePeriod]:
    """Insert or replace a price period, keeping the list sorted by start."""
    kept = [p for p in history if p.start != period.start]
    kept.append(period)
    return sorted(kept, key=lambda p: p.start)


def price_on(history: list[PricePeriod], day: date) -> PricePeriod:
    """Price in force on ``day`` (the earliest known one before history starts)."""
    if not history:
        raise ValueError("Sin precios")
    current = history[0]
    for period in history:
        if period.start <= day:
            current = period
    return current


@dataclass
class BillLine:
    """One line of the bill."""

    concept: str
    start: date | None
    end: date | None
    quantity: float
    unit: str
    rate: float
    rate_unit: str
    amount: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "concepto": self.concept,
            "desde": self.start.isoformat() if self.start else None,
            "hasta": self.end.isoformat() if self.end else None,
            "cantidad": self.quantity,
            "unidad": self.unit,
            "precio": self.rate,
            "unidad_precio": self.rate_unit,
            "importe": self.amount,
        }


@dataclass
class Bill:
    """Bill estimate between two meter readings."""

    start: date
    end: date
    days: int
    m3: int
    kwh: int
    factor: float
    lines: list[BillLine] = field(default_factory=list)
    base: float = 0.0
    vat_rate: float = 21.0
    vat: float = 0.0
    total: float = 0.0
    forecast: float = 0.0
    period_days: int = 61

    def as_attributes(self) -> dict[str, Any]:
        return {
            "fecha_lectura_anterior": self.start.isoformat(),
            "hasta": self.end.isoformat(),
            "dias": self.days,
            "m3": self.m3,
            "kwh": self.kwh,
            "factor_conversion": self.factor,
            "lineas": [line.as_dict() for line in self.lines],
            "base_imponible": self.base,
            "iva_porcentaje": self.vat_rate,
            "iva": self.vat,
            "total": self.total,
            "prevision": self.forecast,
            "dias_periodo": self.period_days,
        }


def compute_bill(
    *,
    last_reading_date: date,
    last_reading: float,
    end_date: date,
    current_reading: float,
    factor: float,
    history: list[PricePeriod],
    ieh: float,
    rental_day: float,
    vat: float,
    period_days: int = 61,
) -> Bill:
    """Reproduce the TUR bill.

    Days run from the day after the previous reading to ``end_date`` inclusive.
    Whole m³ are billed, converted to whole kWh; when the price changes inside
    the period, fixed term and kWh are split by days, each line rounded to cents.
    """
    days = max((end_date - last_reading_date).days, 0)
    m3 = max(int(current_reading) - int(last_reading), 0)
    kwh = round_int(m3 * factor)
    bill = Bill(
        start=last_reading_date,
        end=end_date,
        days=days,
        m3=m3,
        kwh=kwh,
        factor=factor,
        vat_rate=vat,
        period_days=period_days,
    )
    if days == 0:
        return bill

    # Split the billing days into stretches with a single price.
    first_day = last_reading_date + timedelta(days=1)
    segments: list[tuple[date, date, PricePeriod]] = []
    day = first_day
    while day <= end_date:
        price = price_on(history, day)
        later = [p.start for p in history if p.start > day]
        seg_end = min(end_date, (min(later) - timedelta(days=1)) if later else end_date)
        segments.append((day, seg_end, price))
        day = seg_end + timedelta(days=1)

    fixed_lines: list[BillLine] = []
    energy_lines: list[BillLine] = []
    kwh_left = kwh
    for index, (seg_start, seg_end, price) in enumerate(segments):
        seg_days = (seg_end - seg_start).days + 1
        rate = daily_fixed(price.fixed_month)
        fixed_lines.append(
            BillLine("Término fijo", seg_start, seg_end, seg_days, "días", rate, "€/día", money(seg_days * rate))
        )
        seg_kwh = kwh_left if index == len(segments) - 1 else round_int(kwh * seg_days / days)
        kwh_left -= seg_kwh
        energy_lines.append(
            BillLine(
                "Consumo gas", seg_start, seg_end, seg_kwh, "kWh", price.variable, "€/kWh",
                money(seg_kwh * price.variable),
            )
        )

    lines = [
        *fixed_lines,
        *energy_lines,
        BillLine("Impuesto hidrocarburos", None, None, kwh, "kWh", ieh, "€/kWh", money(kwh * ieh)),
        BillLine("Alquiler de contador", None, None, days, "días", rental_day, "€/día", money(days * rental_day)),
    ]
    bill.lines = lines
    bill.base = money(sum(line.amount for line in lines))
    bill.vat = money(bill.base * vat / 100)
    bill.total = money(bill.base + bill.vat)
    bill.forecast = money(bill.total / days * period_days)
    return bill


def price_per_m3(variable: float, ieh: float, factor: float, vat: float) -> float:
    """Price of one m³ with hydrocarbon tax and VAT."""
    return round((variable + ieh) * factor * (1 + vat / 100), 4)


def fixed_per_day_taxed(fixed_month: float, rental_day: float, vat: float) -> float:
    """Fixed cost of one day (fixed term + meter rental) with VAT."""
    return round((daily_fixed(fixed_month) + rental_day) * (1 + vat / 100), 6)
