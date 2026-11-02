"""End-to-end tests in a real Home Assistant (pytest-homeassistant-custom-component)."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant import config_entries  # noqa: E402
from homeassistant.components import frontend  # noqa: E402
from homeassistant.config_entries import ConfigEntryState  # noqa: E402
from homeassistant.core import HomeAssistant  # noqa: E402
from homeassistant.data_entry_flow import FlowResultType  # noqa: E402
from homeassistant.helpers import entity_registry as er  # noqa: E402
from homeassistant.util import dt as dt_util  # noqa: E402
from pytest_homeassistant_custom_component.common import (  # noqa: E402
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.gas_tur.const import DOMAIN  # noqa: E402

from .conftest import PAGE, TUR2_URL  # noqa: E402


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom_components/ in every test."""
    return


@pytest.fixture(autouse=True)
async def madrid(hass):
    """Bills and days follow Spanish local time."""
    await hass.config.async_set_time_zone("Europe/Madrid")


@pytest.fixture
def expected_lingering_timers() -> bool:
    """Delayed storage writes may still be pending when a test ends."""
    return True


@pytest.fixture
def prices(aioclient_mock):
    """The TUR 2 page as of October 2026."""
    aioclient_mock.get(TUR2_URL, text=PAGE)
    return aioclient_mock


PULSE = "binary_sensor.contador_gas_contact"

BASE = {
    "pulse_entity": PULSE,
    "edge": "on_off",
    "m3_per_pulse": 0.01,
    "tariff": "tur2",
    "initial_reading": 22814.45,
    "create_dashboard": False,
    "bill_date": "2026-10-21",
    "bill_reading": 22814,
    "factor": 10.318,
    "rental": 0.019068,
}


def make_entry(**data) -> MockConfigEntry:
    return MockConfigEntry(domain=DOMAIN, title="Gas", data={**BASE, **data}, unique_id=PULSE)


async def setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    hass.states.async_set(PULSE, "off")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def eid(hass: HomeAssistant, entry: MockConfigEntry, key: str, platform: str = "sensor") -> str:
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}")
    assert entity_id, key
    return entity_id


def state(hass, entry, key, platform="sensor"):
    return hass.states.get(eid(hass, entry, key, platform))


async def pulse(hass: HomeAssistant, freezer, seconds: float = 30) -> None:
    freezer.tick(timedelta(seconds=seconds))
    hass.states.async_set(PULSE, "on")
    await hass.async_block_till_done()
    hass.states.async_set(PULSE, "off")
    await hass.async_block_till_done()


async def test_config_flow(hass: HomeAssistant, prices) -> None:
    hass.states.async_set(PULSE, "off")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Gas",
            "pulse_entity": PULSE,
            "edge": "on_off",
            "m3_per_pulse": 0.01,
            "tariff": "tur2",
            "initial_reading": 22814.45,
            "create_dashboard": False,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "bill"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"bill_date": "2026-10-21", "bill_reading": 22814, "factor": 10.318, "rental": 0.019068},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Gas"
    assert result["data"]["pulse_entity"] == PULSE
    assert result["data"]["factor"] == 10.318
    await hass.async_block_till_done()

    again = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    again = await hass.config_entries.flow.async_configure(
        again["flow_id"],
        {
            "name": "Gas 2",
            "pulse_entity": PULSE,
            "edge": "on_off",
            "m3_per_pulse": 0.01,
            "tariff": "tur2",
            "initial_reading": 1,
            "create_dashboard": False,
        },
    )
    assert again["type"] is FlowResultType.ABORT
    assert again["reason"] == "already_configured"


async def test_options_flow(hass: HomeAssistant, prices, freezer) -> None:
    freezer.move_to("2026-11-02 12:00:00+01:00")
    entry = make_entry()
    await setup(hass, entry)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "pulse_entity": PULSE,
            "edge": "off_on",
            "m3_per_pulse": 0.01,
            "tariff": "tur2",
            "debounce": 1,
            "auto_prices": True,
            "period_days": 60,
            "create_dashboard": False,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.period_days == 60

    # Now off -> on counts.
    hass.states.async_set(PULSE, "on")
    await hass.async_block_till_done()
    assert state(hass, entry, "lectura").state == "22814.46"


async def test_setup_and_prices(hass: HomeAssistant, prices, freezer) -> None:
    freezer.move_to("2026-11-02 12:00:00+01:00")
    entry = make_entry()
    await setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED

    assert state(hass, entry, "lectura").state == "22814.45"
    price = state(hass, entry, "precio_kwh")
    assert price.state == "0.050428"
    assert price.attributes["tarifa"] == "TUR 2"
    assert price.attributes["vigente_desde"] == "2026-10-01"
    assert price.attributes["proxima_revision"] == "2027-01-01"
    assert state(hass, entry, "termino_fijo").state == "8.17"
    assert state(hass, entry, "estado_precios").state == "ok"
    # Hydrocarbon tax derived from the taxed price on the page.
    assert state(hass, entry, "impuesto_hidrocarburos", "number").state == "0.00234"
    assert float(state(hass, entry, "precio_m3").state) == pytest.approx(
        (0.050428 + 0.00234) * 10.318 * 1.21, abs=1e-4
    )
    assert state(hass, entry, "fecha_factura", "date").state == "2026-10-21"
    bill = state(hass, entry, "factura")
    assert bill.attributes["dias"] == 12
    assert bill.attributes["m3"] == 0
    # 12 days of fixed term + rental, with VAT: (3.22 + 0.23) * 1.21
    assert bill.state == "4.17"


async def test_pulses_flow_and_debounce(hass: HomeAssistant, prices, freezer) -> None:
    freezer.move_to("2026-11-02 12:00:00+01:00")
    entry = make_entry()
    await setup(hass, entry)

    for _ in range(3):
        await pulse(hass, freezer, 30)
    assert state(hass, entry, "lectura").state == "22814.48"
    assert state(hass, entry, "consumo_hoy").state == "0.03"
    assert state(hass, entry, "consumo_mes").state == "0.03"
    assert float(state(hass, entry, "caudal").state) == pytest.approx(1.2)
    assert state(hass, entry, "ultimo_pulso").state != "unknown"

    # Bounce: a pulse 0.2 s later is ignored.
    await pulse(hass, freezer, 0.2)
    assert state(hass, entry, "lectura").state == "22814.48"

    # Wrong direction and coming back from unavailable are ignored.
    hass.states.async_set(PULSE, "on")
    await hass.async_block_till_done()
    hass.states.async_set(PULSE, "unavailable")
    await hass.async_block_till_done()
    hass.states.async_set(PULSE, "off")
    await hass.async_block_till_done()
    assert state(hass, entry, "lectura").state == "22814.48"

    # Flow decays and drops to zero after 15 minutes without pulses.
    freezer.tick(timedelta(minutes=16))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert state(hass, entry, "caudal").state == "0.0"

    # Cost today = 0.03 m³ × price + fixed day.
    cost = float(state(hass, entry, "coste_hoy").state)
    price_m3 = float(state(hass, entry, "precio_m3").state)
    fixed = float(state(hass, entry, "fijo_dia").state)
    assert cost == pytest.approx(round(0.03 * price_m3 + fixed, 2))


async def test_day_rollover_and_persistence(hass: HomeAssistant, prices, freezer) -> None:
    freezer.move_to("2026-11-02 23:59:00+01:00")
    entry = make_entry()
    await setup(hass, entry)
    await pulse(hass, freezer, 10)
    assert state(hass, entry, "consumo_hoy").state == "0.01"

    freezer.move_to("2026-11-03 00:00:30+01:00")
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert state(hass, entry, "consumo_hoy").state == "0.0"
    assert state(hass, entry, "consumo_mes").state == "0.01"

    # Reload keeps the reading.
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert state(hass, entry, "lectura").state == "22814.46"


async def test_october_bill_to_the_cent(hass: HomeAssistant, prices, freezer) -> None:
    """The real bill of 21/10/2026: 41,77 €."""
    freezer.move_to("2026-10-21 20:00:00+02:00")
    entry = make_entry()
    await setup(hass, entry)

    await hass.services.async_call(
        DOMAIN,
        "establecer_precio",
        {"fecha": "2026-07-01", "termino_fijo": 8.11, "termino_variable": 0.041199},
        blocking=True,
    )
    await hass.services.async_call(
        DOMAIN,
        "nueva_factura",
        {"fecha": "2026-08-24", "lectura": 22777, "factor_conversion": 10.318},
        blocking=True,
    )
    bill = state(hass, entry, "factura")
    assert bill.state == "41.77"
    assert bill.attributes["dias"] == 58
    assert bill.attributes["m3"] == 37
    assert bill.attributes["kwh"] == 382
    assert [line["importe"] for line in bill.attributes["lineas"]] == [9.87, 5.64, 10.05, 6.96, 0.89, 1.11]
    assert bill.attributes["base_imponible"] == 34.52
    assert bill.attributes["iva"] == 7.25

    # Closing that bill starts a new period at 0 days.
    await hass.services.async_call(
        DOMAIN, "nueva_factura", {"fecha": "2026-10-21", "lectura": 22814}, blocking=True
    )
    assert state(hass, entry, "factura").attributes["dias"] == 0
    assert state(hass, entry, "lectura_factura", "number").state == "22814.0"


async def test_adjust_reading(hass: HomeAssistant, prices, freezer) -> None:
    freezer.move_to("2026-11-02 12:00:00+01:00")
    entry = make_entry()
    await setup(hass, entry)
    await pulse(hass, freezer)
    await hass.services.async_call(DOMAIN, "ajustar_lectura", {"lectura": 22830.0}, blocking=True)
    assert state(hass, entry, "lectura").state == "22830.0"
    assert state(hass, entry, "consumo_hoy").state == "0.01"

    # The same from the number entity.
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": eid(hass, entry, "ajuste_lectura", "number"), "value": 22831.5},
        blocking=True,
    )
    assert state(hass, entry, "lectura").state == "22831.5"


async def test_number_and_date_entities(hass: HomeAssistant, prices, freezer) -> None:
    freezer.move_to("2026-11-02 12:00:00+01:00")
    entry = make_entry()
    await setup(hass, entry)
    await hass.services.async_call(
        "number", "set_value",
        {"entity_id": eid(hass, entry, "factor_conversion", "number"), "value": 10.462},
        blocking=True,
    )
    await hass.services.async_call(
        "date", "set_value",
        {"entity_id": eid(hass, entry, "fecha_factura", "date"), "date": "2026-10-01"},
        blocking=True,
    )
    bill = state(hass, entry, "factura")
    assert bill.attributes["factor_conversion"] == 10.462
    assert bill.attributes["dias"] == 32


async def test_price_error_keeps_last_price(hass: HomeAssistant, aioclient_mock, freezer) -> None:
    freezer.move_to("2026-11-02 12:00:00+01:00")
    aioclient_mock.get(TUR2_URL, status=500)
    entry = make_entry()
    await setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    assert state(hass, entry, "estado_precios").state == "error"
    assert state(hass, entry, "precio_kwh").state == "unknown"
    assert state(hass, entry, "factura").state == "unknown"

    # Manual price still gives a bill.
    await hass.services.async_call(
        DOMAIN, "establecer_precio",
        {"fecha": "2026-10-01", "termino_fijo": 8.17, "termino_variable": 0.050428},
        blocking=True,
    )
    assert state(hass, entry, "factura").state == "4.17"


async def test_price_change_is_recorded(hass: HomeAssistant, aioclient_mock, freezer) -> None:
    freezer.move_to("2026-12-30 12:00:00+01:00")
    aioclient_mock.get(TUR2_URL, text=PAGE)
    entry = make_entry()
    await setup(hass, entry)

    aioclient_mock.clear_requests()
    aioclient_mock.get(TUR2_URL, text=PAGE.replace("0,050428", "0,046000").replace("0,063849", "0,058491"))
    freezer.move_to("2027-01-01 10:00:00+01:00")
    await hass.services.async_call(DOMAIN, "actualizar_precios", {}, blocking=True)
    await hass.async_block_till_done()

    price = state(hass, entry, "precio_kwh")
    assert price.state == "0.046"
    assert [p["start"] for p in price.attributes["historial"]] == ["2027-01-01", "2026-10-01"]


async def test_dashboard(hass: HomeAssistant, prices, freezer) -> None:
    from homeassistant.components.lovelace.dashboard import LovelaceYAML

    freezer.move_to("2026-11-02 12:00:00+01:00")
    hass.data["lovelace"] = SimpleNamespace(dashboards={})
    entry = make_entry(create_dashboard=True)
    await setup(hass, entry)

    dashboards = hass.data["lovelace"].dashboards
    assert isinstance(dashboards["gas-tur"], LovelaceYAML)
    assert frontend.async_panel_exists(hass, "gas-tur")
    config = await dashboards["gas-tur"].async_load(False)
    view = config["views"][0]
    assert [s["cards"][0]["heading"] for s in view["sections"]] == [
        "Hoy", "Factura en curso", "Precios", "Histórico",
    ]
    text = str(config)
    assert eid(hass, entry, "factura") in text
    assert "@factura" not in text

    # Reload re-registers without errors, unload removes it.
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert frontend.async_panel_exists(hass, "gas-tur")
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert not frontend.async_panel_exists(hass, "gas-tur")
    assert "gas-tur" not in dashboards


async def test_dashboard_does_not_overwrite_user_panel(hass: HomeAssistant, prices, freezer) -> None:
    freezer.move_to("2026-11-02 12:00:00+01:00")
    hass.data["lovelace"] = SimpleNamespace(dashboards={"gas-tur": object()})
    entry = make_entry(create_dashboard=True)
    await setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    assert not frontend.async_panel_exists(hass, "gas-tur")


async def test_unload_and_remove(hass: HomeAssistant, prices, freezer, hass_storage) -> None:
    freezer.move_to("2026-11-02 12:00:00+01:00")
    entry = make_entry()
    await setup(hass, entry)
    await pulse(hass, freezer)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass_storage[f"{DOMAIN}.{entry.entry_id}"]["data"]["reading"] == 22814.46
    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert f"{DOMAIN}.{entry.entry_id}" not in hass_storage
