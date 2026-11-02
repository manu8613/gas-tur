"""Config flow for Gas TUR."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    DateSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)
from homeassistant.util import dt as dt_util

from .compat import vol
from .const import (
    CONF_AUTO_PRICES,
    CONF_BILL_DATE,
    CONF_BILL_READING,
    CONF_CREATE_DASHBOARD,
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
    DEFAULT_M3_PER_PULSE,
    DEFAULT_NAME,
    DEFAULT_PERIOD_DAYS,
    DEFAULT_RENTAL,
    DEFAULT_TARIFF,
    DOMAIN,
    EDGE_OFF_ON,
    EDGE_ON_OFF,
    TARIFF_URLS,
)


def _number(minimum: float, maximum: float, step: float, unit: str | None = None) -> NumberSelector:
    config = NumberSelectorConfig(
        min=minimum,
        max=maximum,
        step=step if step >= 0.001 else "any",  # selectors refuse steps below 0.001
        mode=NumberSelectorMode.BOX,
    )
    if unit:
        config["unit_of_measurement"] = unit
    return NumberSelector(config)


def _select(options: list[str], key: str) -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(options=options, translation_key=key, mode=SelectSelectorMode.DROPDOWN)
    )


def _meter_fields(values: dict[str, Any]) -> dict[Any, Any]:
    """Fields shared by setup and options: pulse sensor, edge, m³/pulse, tariff."""
    pulse = (
        vol.Required(CONF_PULSE_ENTITY, default=values[CONF_PULSE_ENTITY])
        if values.get(CONF_PULSE_ENTITY)
        else vol.Required(CONF_PULSE_ENTITY)
    )
    return {
        pulse: EntitySelector(EntitySelectorConfig(domain="binary_sensor")),
        vol.Required(CONF_EDGE, default=values.get(CONF_EDGE, EDGE_ON_OFF)): _select(
            [EDGE_ON_OFF, EDGE_OFF_ON], CONF_EDGE
        ),
        vol.Required(
            CONF_M3_PER_PULSE, default=values.get(CONF_M3_PER_PULSE, DEFAULT_M3_PER_PULSE)
        ): _number(0.0001, 10, 0.0001, "m³"),
        vol.Required(CONF_TARIFF, default=values.get(CONF_TARIFF, DEFAULT_TARIFF)): _select(
            list(TARIFF_URLS), CONF_TARIFF
        ),
    }


class GasTurConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a gas meter."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_PULSE_ENTITY])
            self._abort_if_unique_id_configured()
            self._data = user_input
            return await self.async_step_bill()

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): TextSelector(),
                **_meter_fields({}),
                vol.Required(CONF_INITIAL_READING): _number(0, 9_999_999, 0.01, "m³"),
                vol.Required(CONF_CREATE_DASHBOARD, default=True): BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_bill(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            data = {**self._data, **user_input}
            return self.async_create_entry(title=data.pop(CONF_NAME), data=data)

        reading = float(self._data[CONF_INITIAL_READING])
        schema = vol.Schema(
            {
                vol.Required(CONF_BILL_DATE, default=dt_util.now().date().isoformat()): DateSelector(),
                vol.Required(CONF_BILL_READING, default=int(reading)): _number(0, 9_999_999, 0.01, "m³"),
                vol.Required(CONF_FACTOR, default=DEFAULT_FACTOR): _number(5, 15, 0.001, "kWh/m³"),
                vol.Required(CONF_RENTAL, default=DEFAULT_RENTAL): _number(0, 2, 0.000001, "€/día"),
            }
        )
        return self.async_show_form(step_id="bill", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> GasTurOptionsFlow:
        return GasTurOptionsFlow()


class GasTurOptionsFlow(OptionsFlow):
    """Change the pulse sensor, tariff and behaviour."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        values = {**self.config_entry.data, **self.config_entry.options}
        schema = vol.Schema(
            {
                **_meter_fields(values),
                vol.Required(
                    CONF_DEBOUNCE, default=values.get(CONF_DEBOUNCE, DEFAULT_DEBOUNCE)
                ): _number(0, 60, 0.1, "s"),
                vol.Required(CONF_AUTO_PRICES, default=values.get(CONF_AUTO_PRICES, True)): BooleanSelector(),
                vol.Required(
                    CONF_PERIOD_DAYS, default=values.get(CONF_PERIOD_DAYS, DEFAULT_PERIOD_DAYS)
                ): _number(1, 366, 1, "días"),
                vol.Required(
                    CONF_CREATE_DASHBOARD, default=values.get(CONF_CREATE_DASHBOARD, True)
                ): BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
