"""State, pulse counting and TUR prices for one gas meter."""

from __future__ import annotations

import asyncio
from datetime import date, datetime
import logging
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_AUTO_PRICES,
    CONF_BILL_DATE,
    CONF_BILL_READING,
    CONF_DEBOUNCE,
    CONF_EDGE,
    CONF_FACTOR,
    CONF_INITIAL_READING,
    CONF_M3_PER_PULSE,
    CONF_PERIOD_DAYS,
    CONF_PULSE_ENTITY,
    CONF_RENTAL,
    CONF_TARIFF,
    DEFAULT_DEBOUNCE,
    DEFAULT_FACTOR,
    DEFAULT_IEH,
    DEFAULT_M3_PER_PULSE,
    DEFAULT_PERIOD_DAYS,
    DEFAULT_RENTAL,
    DEFAULT_TARIFF,
    DEFAULT_VAT,
    DOMAIN,
    EDGE_OFF_ON,
    FLOW_TIMEOUT,
    KEY_BILL_DATE,
    KEY_BILL_READING,
    KEY_FACTOR,
    KEY_IEH,
    KEY_RENTAL,
    KEY_VAT,
    MAX_FLOW,
    PRICE_REFRESH,
    STORAGE_VERSION,
    TARIFF_URLS,
    TICK,
)
from .tariff import (
    Bill,
    PricePeriod,
    add_price,
    compute_bill,
    derive_ieh,
    effective_date,
    fixed_per_day_taxed,
    money,
    parse_prices,
    price_on,
    price_per_m3,
    quarter_start,
)

_LOGGER = logging.getLogger(__name__)

type GasTurConfigEntry = ConfigEntry[GasTurManager]


class GasTurManager(DataUpdateCoordinator[None]):
    """Counts pulses, keeps the reading and fetches the TUR prices."""

    config_entry: GasTurConfigEntry

    def __init__(self, hass: HomeAssistant, entry: GasTurConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=PRICE_REFRESH,
        )
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self.reading: float = 0.0
        self.day: str = ""
        self.day_start: float = 0.0
        self.month: str = ""
        self.month_start: float = 0.0
        self.last_pulse: datetime | None = None
        self.flow: float = 0.0
        self.prices: list[PricePeriod] = []
        self.price_checked: datetime | None = None
        self.price_error: str | None = None
        self.settings: dict[str, Any] = {}

    # ------------------------------------------------------------------ options
    def _opt(self, key: str, default: Any) -> Any:
        entry = self.config_entry
        return entry.options.get(key, entry.data.get(key, default))

    @property
    def pulse_entity(self) -> str:
        return self._opt(CONF_PULSE_ENTITY, "")

    @property
    def m3_per_pulse(self) -> float:
        return float(self._opt(CONF_M3_PER_PULSE, DEFAULT_M3_PER_PULSE))

    @property
    def tariff(self) -> str:
        return self._opt(CONF_TARIFF, DEFAULT_TARIFF)

    @property
    def auto_prices(self) -> bool:
        return bool(self._opt(CONF_AUTO_PRICES, True))

    @property
    def period_days(self) -> int:
        return int(self._opt(CONF_PERIOD_DAYS, DEFAULT_PERIOD_DAYS))

    # ---------------------------------------------------------------- lifecycle
    async def async_load(self) -> None:
        """Restore the saved state, or start from the setup values."""
        data = await self._store.async_load()
        entry = self.config_entry.data
        today = dt_util.now().date()
        if data is None:
            self.reading = float(entry.get(CONF_INITIAL_READING, 0.0))
            self.settings = {
                KEY_FACTOR: float(entry.get(CONF_FACTOR, DEFAULT_FACTOR)),
                KEY_IEH: DEFAULT_IEH,
                KEY_RENTAL: float(entry.get(CONF_RENTAL, DEFAULT_RENTAL)),
                KEY_VAT: DEFAULT_VAT,
                KEY_BILL_READING: float(entry.get(CONF_BILL_READING, self.reading)),
                KEY_BILL_DATE: entry.get(CONF_BILL_DATE, today.isoformat()),
            }
            self.day = today.isoformat()
            self.day_start = self.reading
            self.month = today.strftime("%Y-%m")
            self.month_start = self.reading
            self._save()
            return
        self.reading = float(data["reading"])
        self.day = data.get("day", today.isoformat())
        self.day_start = float(data.get("day_start", self.reading))
        self.month = data.get("month", today.strftime("%Y-%m"))
        self.month_start = float(data.get("month_start", self.reading))
        if last := data.get("last_pulse"):
            self.last_pulse = dt_util.parse_datetime(last)
        self.prices = [PricePeriod.from_dict(p) for p in data.get("prices", [])]
        if checked := data.get("price_checked"):
            self.price_checked = dt_util.parse_datetime(checked)
        self.price_error = data.get("price_error")
        self.settings = data["settings"]

    def _data_to_save(self) -> dict[str, Any]:
        return {
            "reading": self.reading,
            "day": self.day,
            "day_start": self.day_start,
            "month": self.month,
            "month_start": self.month_start,
            "last_pulse": self.last_pulse.isoformat() if self.last_pulse else None,
            "prices": [p.as_dict() for p in self.prices],
            "price_checked": self.price_checked.isoformat() if self.price_checked else None,
            "price_error": self.price_error,
            "settings": self.settings,
        }

    @callback
    def _save(self) -> None:
        self._store.async_delay_save(self._data_to_save, 5)

    async def async_flush(self) -> None:
        """Write the state now (on unload)."""
        await self._store.async_save(self._data_to_save())

    async def async_remove_store(self) -> None:
        await self._store.async_remove()

    @callback
    def async_start(self) -> None:
        """Start listening to the pulse sensor and the clock."""
        entry = self.config_entry
        entry.async_on_unload(
            async_track_state_change_event(self.hass, [self.pulse_entity], self._handle_pulse)
        )
        entry.async_on_unload(async_track_time_interval(self.hass, self._tick, TICK))
        entry.async_on_unload(
            async_track_time_change(self.hass, self._midnight, hour=0, minute=0, second=1)
        )
        self._rollover()

    # ------------------------------------------------------------------ pulses
    @callback
    def _handle_pulse(self, event: Event[EventStateChangedData]) -> None:
        old, new = event.data["old_state"], event.data["new_state"]
        if old is None or new is None:
            return
        if old.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return
        edge = self._opt(CONF_EDGE, "on_off")
        before, after = ("off", "on") if edge == EDGE_OFF_ON else ("on", "off")
        if old.state != before or new.state != after:
            return
        now = dt_util.utcnow()
        if self.last_pulse is not None:
            interval = (now - self.last_pulse).total_seconds()
            if interval < float(self._opt(CONF_DEBOUNCE, DEFAULT_DEBOUNCE)):
                return
            if interval < FLOW_TIMEOUT.total_seconds():
                self.flow = min(round(self.m3_per_pulse * 3600 / interval, 3), MAX_FLOW)
        self.last_pulse = now
        self._rollover()
        self.reading = round(self.reading + self.m3_per_pulse, 4)
        self._save()
        self.async_update_listeners()

    @callback
    def _tick(self, now: datetime) -> None:
        """Let the flow fall when pulses stop."""
        if self.last_pulse is None or self.flow == 0:
            return
        since = (dt_util.utcnow() - self.last_pulse).total_seconds()
        flow = 0.0 if since >= FLOW_TIMEOUT.total_seconds() else min(
            self.flow, round(self.m3_per_pulse * 3600 / max(since, 1), 3)
        )
        if flow != self.flow:
            self.flow = flow
            self.async_update_listeners()

    @callback
    def _midnight(self, now: datetime) -> None:
        if self._rollover():
            self.async_update_listeners()

    @callback
    def _rollover(self) -> bool:
        """Start a new day or month. Returns True if anything changed."""
        today = dt_util.now().date()
        changed = False
        if self.day != today.isoformat():
            self.day, self.day_start = today.isoformat(), self.reading
            changed = True
        if self.month != today.strftime("%Y-%m"):
            self.month, self.month_start = today.strftime("%Y-%m"), self.reading
            changed = True
        if changed:
            self._save()
        return changed

    # ------------------------------------------------------------------ prices
    async def _async_update_data(self) -> None:
        """Fetch the TUR prices. Never fails: keeps the last known prices."""
        if not self.auto_prices:
            return
        url = TARIFF_URLS[self.tariff]
        session = async_get_clientsession(self.hass)
        try:
            async with asyncio.timeout(30):
                response = await session.get(url, headers={"User-Agent": "HomeAssistant gas_tur"})
                response.raise_for_status()
                page = await response.text()
            parsed = parse_prices(page)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            if self.price_error is None:
                _LOGGER.warning("No se pudieron leer los precios TUR de %s: %s", url, err)
            self.price_error = str(err) or type(err).__name__
            self.price_checked = dt_util.utcnow()
            self._save()
            return
        self.price_error = None
        self.price_checked = dt_util.utcnow()
        today = dt_util.now().date()
        latest = self.prices[-1] if self.prices else None
        if (
            latest is None
            or abs(latest.variable - parsed.variable) > 1e-7
            or abs(latest.fixed_month - parsed.fixed_month) > 1e-4
        ):
            start = quarter_start(today) if latest is None else effective_date(today)
            self.prices = add_price(
                self.prices, PricePeriod(start, parsed.fixed_month, parsed.variable)
            )
            _LOGGER.info(
                "Precio TUR %s desde %s: %s €/mes, %s €/kWh",
                self.tariff.upper(), start, parsed.fixed_month, parsed.variable,
            )
        ieh = derive_ieh(parsed, float(self.settings[KEY_VAT]))
        if ieh is not None and abs(ieh - float(self.settings[KEY_IEH])) > 5e-7:
            _LOGGER.info("Impuesto de hidrocarburos actualizado a %s €/kWh", ieh)
            self.settings[KEY_IEH] = ieh
        self._save()

    @callback
    def async_set_price(self, start: date, fixed_month: float, variable: float) -> None:
        self.prices = add_price(self.prices, PricePeriod(start, fixed_month, variable))
        self._save()
        self.async_update_listeners()

    # ---------------------------------------------------------------- settings
    @callback
    def async_set_setting(self, key: str, value: Any) -> None:
        self.settings[key] = value
        self._save()
        self.async_update_listeners()

    @callback
    def async_set_reading(self, value: float) -> None:
        """Set the meter reading. Today's and this month's use are not affected."""
        delta = round(value - self.reading, 4)
        self._rollover()
        self.reading = round(value, 4)
        self.day_start = round(self.day_start + delta, 4)
        self.month_start = round(self.month_start + delta, 4)
        self._save()
        self.async_update_listeners()

    @callback
    def async_new_bill(self, bill_date: date, reading: float, factor: float | None) -> None:
        self.settings[KEY_BILL_DATE] = bill_date.isoformat()
        self.settings[KEY_BILL_READING] = float(reading)
        if factor is not None:
            self.settings[KEY_FACTOR] = float(factor)
        self._save()
        self.async_update_listeners()

    # ------------------------------------------------------------- calculation
    @property
    def factor(self) -> float:
        return float(self.settings[KEY_FACTOR])

    @property
    def ieh(self) -> float:
        return float(self.settings[KEY_IEH])

    @property
    def vat(self) -> float:
        return float(self.settings[KEY_VAT])

    @property
    def rental(self) -> float:
        return float(self.settings[KEY_RENTAL])

    @property
    def bill_date(self) -> date:
        return date.fromisoformat(self.settings[KEY_BILL_DATE])

    @property
    def bill_reading(self) -> float:
        return float(self.settings[KEY_BILL_READING])

    @property
    def price(self) -> PricePeriod | None:
        return price_on(self.prices, dt_util.now().date()) if self.prices else None

    @property
    def m3_today(self) -> float:
        return round(max(self.reading - self.day_start, 0.0), 3)

    @property
    def m3_month(self) -> float:
        return round(max(self.reading - self.month_start, 0.0), 3)

    @property
    def m3_since_bill(self) -> float:
        return round(max(self.reading - self.bill_reading, 0.0), 3)

    @property
    def price_m3(self) -> float | None:
        if (price := self.price) is None:
            return None
        return price_per_m3(price.variable, self.ieh, self.factor, self.vat)

    @property
    def fixed_day(self) -> float | None:
        if (price := self.price) is None:
            return None
        return fixed_per_day_taxed(price.fixed_month, self.rental, self.vat)

    @property
    def cost_today(self) -> float | None:
        if self.price_m3 is None or self.fixed_day is None:
            return None
        return money(self.m3_today * self.price_m3 + self.fixed_day)

    @property
    def cost_month(self) -> float | None:
        if self.price_m3 is None or self.fixed_day is None:
            return None
        return money(self.m3_month * self.price_m3 + self.fixed_day * dt_util.now().day)

    @property
    def bill(self) -> Bill | None:
        if not self.prices:
            return None
        return compute_bill(
            last_reading_date=self.bill_date,
            last_reading=self.bill_reading,
            end_date=dt_util.now().date(),
            current_reading=self.reading,
            factor=self.factor,
            history=self.prices,
            ieh=self.ieh,
            rental_day=self.rental,
            vat=self.vat,
            period_days=self.period_days,
        )
