"""Lovelace dashboard for Gas TUR (pure data, no Home Assistant imports).

Uses Mushroom, ApexCharts card and card-mod from HACS.
"""

from __future__ import annotations

from typing import Any

# Entity keys -> (platform, unique_id suffix)
ENTITY_KEYS: dict[str, str] = {
    "lectura": "sensor",
    "consumo_hoy": "sensor",
    "consumo_mes": "sensor",
    "consumo_factura": "sensor",
    "caudal": "sensor",
    "ultimo_pulso": "sensor",
    "precio_kwh": "sensor",
    "termino_fijo": "sensor",
    "precio_m3": "sensor",
    "fijo_dia": "sensor",
    "coste_hoy": "sensor",
    "coste_mes": "sensor",
    "factura": "sensor",
    "prevision_factura": "sensor",
    "estado_precios": "sensor",
    "factor_conversion": "number",
    "lectura_factura": "number",
    "impuesto_hidrocarburos": "number",
    "alquiler_contador": "number",
    "iva": "number",
    "ajuste_lectura": "number",
    "fecha_factura": "date",
}

_MACROS = """{%- macro n(x, d=2) -%}{{ ('%.' ~ d ~ 'f') | format(x | float(0)) | replace('.', ',') }}{%- endmacro -%}
{%- macro fecha(s) -%}{{ s[8:10] ~ '/' ~ s[5:7] ~ '/' ~ s[0:4] if s else '—' }}{%- endmacro -%}
"""

_TODAY = _MACROS + """{%- set coste = states('@coste_hoy') | float(0) -%}
{%- set m3 = states('@consumo_hoy') | float(0) -%}
{%- set factor = states('@factor_conversion') | float(0) -%}
{%- set mes = states('@coste_mes') | float(0) -%}
{%- set m3_mes = states('@consumo_mes') | float(0) -%}
<ha-icon icon="mdi:fire"></ha-icon> **Gasto de hoy**

# {{ n(coste) }} €

{{ n(m3) }} m³ · {{ n(m3 * factor, 1) }} kWh

Este mes: **{{ n(mes) }} €** · {{ n(m3_mes) }} m³ · media **{{ n(mes / now().day) }} €/día**
"""

_BILL = _MACROS + """{%- set f = '@factura' -%}
{%- set lineas = state_attr(f, 'lineas') -%}
{%- if lineas -%}
Desde el **{{ fecha(state_attr(f, 'fecha_lectura_anterior')) }}** · {{ state_attr(f, 'dias') }} días · **{{ state_attr(f, 'm3') }} m³** → {{ state_attr(f, 'kwh') }} kWh (× {{ n(state_attr(f, 'factor_conversion'), 3) }})

| Concepto | Cálculo | Importe |
|:--|:--|--:|
{%- for l in lineas %}
| {{ l.concepto }}{% if l.desde %}<br><sub>{{ fecha(l.desde) }} – {{ fecha(l.hasta) }}</sub>{% endif %} | {{ l.cantidad }} {{ l.unidad }} × {{ n(l.precio, 6) }} {{ l.unidad_precio }} | {{ n(l.importe) }} € |
{%- endfor %}
| **Base imponible** | | **{{ n(state_attr(f, 'base_imponible')) }} €** |
| IVA | {{ n(state_attr(f, 'iva_porcentaje'), 0) }} % | {{ n(state_attr(f, 'iva')) }} € |
| **Total hasta hoy** | | **{{ n(state_attr(f, 'total')) }} €** |

<ha-icon icon="mdi:crystal-ball"></ha-icon> Previsión a {{ state_attr(f, 'dias_periodo') }} días: **{{ n(state_attr(f, 'prevision')) }} €**

<sub>Como la factura: m³ enteros, kWh redondeados, cambios de precio repartidos por días.</sub>
{%- elif state_attr(f, 'dias') == 0 -%}
Factura recién cerrada el **{{ fecha(state_attr(f, 'fecha_lectura_anterior')) }}**. Mañana empieza a contar.
{%- else -%}
Esperando los precios TUR.
{%- endif %}
"""

_PRICES = _MACROS + """{%- set p = '@precio_kwh' -%}
{%- set var = states(p) | float(0) -%}
{%- set fijo = state_attr(p, 'termino_fijo_mes') | float(0) -%}
{%- set ieh = states('@impuesto_hidrocarburos') | float(0) -%}
{%- set iva = states('@iva') | float(21) -%}
{%- set factor = states('@factor_conversion') | float(0) -%}
{%- set fd = states('@fijo_dia') | float(0) -%}
{%- set k = 1 + iva / 100 -%}
**{{ state_attr(p, 'tarifa') }}** · vigente desde el {{ fecha(state_attr(p, 'vigente_desde')) }}

| Concepto | Sin impuestos | Con impuestos |
|:--|--:|--:|
| Energía | {{ n(var, 6) }} €/kWh | {{ n((var + ieh) * k, 6) }} €/kWh |
| Por m³ | {{ n(var * factor, 4) }} €/m³ | **{{ n(states('@precio_m3'), 4) }} €/m³** |
| Término fijo | {{ n(fijo) }} €/mes | {{ n(fijo * k) }} €/mes |
| Fijo + contador | {{ n(fd / k, 4) }} €/día | {{ n(fd, 4) }} €/día |
| Imp. hidrocarburos | {{ n(ieh, 6) }} €/kWh | |
| Conversión | {{ n(factor, 3) }} kWh/m³ | |
{%- set h = state_attr(p, 'historial') or [] %}
{%- if h | count > 1 %}

**Historial de precios**

| Desde | Término fijo | Término variable |
|:--|--:|--:|
{%- for x in h %}
| {{ fecha(x.start) }} | {{ n(x.fixed_month) }} €/mes | {{ n(x.variable, 6) }} €/kWh |
{%- endfor %}
{%- endif %}

{% set e = states('@estado_precios') -%}
{%- if e == 'ok' -%}<ha-icon icon="mdi:check-circle"></ha-icon> Precios al día desde la Comercializadora Regulada.
{%- elif e == 'manual' -%}<ha-icon icon="mdi:hand-back-right"></ha-icon> Precios en modo manual.
{%- else -%}<ha-icon icon="mdi:alert"></ha-icon> No se pudo leer la web de precios: {{ state_attr('@estado_precios', 'error') }}
{%- endif %}

<ha-icon icon="mdi:calendar-clock"></ha-icon> Próxima revisión: **{{ fecha(state_attr(p, 'proxima_revision')) }}**
"""

_GRADIENT = {
    "style": {
        ".": (
            "ha-card {\n"
            "  background: linear-gradient(135deg, #ff8a00 0%, #e52e71 100%);\n"
            "  color: white;\n"
            "  --primary-text-color: white;\n"
            "  --secondary-text-color: rgba(255, 255, 255, 0.85);\n"
            "  border: none;\n"
            "  box-shadow: 0 6px 20px rgba(229, 46, 113, 0.35);\n"
            "}\n"
        ),
        "ha-markdown$": (
            "h1 { font-size: 3.2em; font-weight: 700; margin: 6px 0 2px; line-height: 1.1; }\n"
            "p { margin: 4px 0; }\n"
        ),
    }
}

_COST_TRANSFORM = (
    "const precio = parseFloat(hass.states['@precio_m3'].state);\n"
    "const fijo = parseFloat(hass.states['@fijo_dia'].state);\n"
    "return x * precio + fijo * {days};"
)


def _fill(value: Any, ids: dict[str, str]) -> Any:
    """Replace @key placeholders with the real entity ids."""
    if isinstance(value, str):
        for key in sorted(ids, key=len, reverse=True):
            value = value.replace(f"@{key}", ids[key])
        return value
    if isinstance(value, list):
        return [_fill(item, ids) for item in value]
    if isinstance(value, dict):
        return {k: _fill(v, ids) for k, v in value.items()}
    return value


def _chart_cost_series(period: str, days: str) -> dict[str, Any]:
    return {
        "entity": "@lectura",
        "name": "Coste aprox. (precio actual)",
        "type": "line",
        "curve": "smooth",
        "stroke_width": 3,
        "color": "#e52e71",
        "yaxis_id": "eur",
        "unit": "€",
        "statistics": {"type": "change", "period": period, "align": "start"},
        "transform": _COST_TRANSFORM.replace("{days}", days),
    }


def _dual_axes(decimals: int) -> list[dict[str, Any]]:
    return [
        {"id": "m3", "min": 0, "decimals": decimals, "apex_config": {"title": {"text": "m³"}}},
        {"id": "eur", "opposite": True, "min": 0, "decimals": decimals, "apex_config": {"title": {"text": "€"}}},
    ]


def build_panel(ids: dict[str, str], title: str) -> dict[str, Any]:
    """Whole dashboard config for one gas meter."""
    today = {
        "type": "grid",
        "cards": [
            {
                "type": "heading",
                "heading": "Hoy",
                "icon": "mdi:fire",
                "badges": [{"type": "entity", "entity": "@ultimo_pulso", "show_state": True, "show_icon": True}],
            },
            {"type": "markdown", "content": _TODAY, "card_mod": _GRADIENT},
            {
                "type": "custom:mushroom-chips-card",
                "alignment": "center",
                "chips": [
                    {
                        "type": "template",
                        "icon": "mdi:currency-eur",
                        "icon_color": "orange",
                        "content": "{{ ('%.3f' | format(states('@precio_m3') | float(0))) | replace('.', ',') }} €/m³",
                        "tap_action": {"action": "more-info"},
                        "entity": "@precio_m3",
                    },
                    {
                        "type": "template",
                        "icon": "mdi:tag-outline",
                        "icon_color": "red",
                        "content": (
                            "{{ state_attr('@precio_kwh', 'tarifa') }} · "
                            "{{ ('%.3f' | format(states('@precio_kwh') | float(0) * 100)) | replace('.', ',') }} c€/kWh"
                        ),
                        "tap_action": {"action": "more-info"},
                        "entity": "@precio_kwh",
                    },
                    {
                        "type": "template",
                        "icon": "mdi:swap-horizontal",
                        "icon_color": "blue",
                        "content": "{{ states('@factor_conversion') | replace('.', ',') }} kWh/m³",
                    },
                ],
            },
            {"type": "tile", "entity": "@caudal", "name": "Caudal", "icon": "mdi:gauge", "color": "light-blue"},
            {"type": "tile", "entity": "@lectura", "name": "Lectura contador", "icon": "mdi:meter-gas", "color": "orange"},
            {"type": "tile", "entity": "@consumo_mes", "name": "Este mes", "icon": "mdi:calendar-month", "color": "deep-orange"},
            {"type": "tile", "entity": "@coste_mes", "name": "Coste del mes", "icon": "mdi:cash", "color": "red"},
        ],
    }

    bill = {
        "type": "grid",
        "cards": [
            {"type": "heading", "heading": "Factura en curso", "icon": "mdi:receipt-text-outline"},
            {"type": "markdown", "content": _BILL},
            {
                "type": "entities",
                "title": "Cerrar factura",
                "icon": "mdi:receipt-text-check-outline",
                "state_color": False,
                "entities": [
                    {
                        "type": "attribute",
                        "entity": "@factura",
                        "attribute": "dias",
                        "name": "Días desde la última lectura",
                        "icon": "mdi:calendar-range",
                    },
                    {"entity": "@fecha_factura", "name": "Fecha de la lectura"},
                    {"entity": "@lectura_factura", "name": "Lectura (m³)"},
                    {"entity": "@factor_conversion", "name": "Factor de conversión"},
                ],
                "footer": {
                    "type": "buttons",
                    "entities": [
                        {
                            "entity": "@prevision_factura",
                            "name": "Previsión",
                            "icon": "mdi:crystal-ball",
                            "show_state": True,
                        }
                    ],
                },
            },
        ],
    }

    prices = {
        "type": "grid",
        "cards": [
            {"type": "heading", "heading": "Precios", "icon": "mdi:tag-outline"},
            {"type": "markdown", "content": _PRICES},
            {
                "type": "entities",
                "title": "Ajustes",
                "icon": "mdi:cog-outline",
                "state_color": False,
                "entities": [
                    {"entity": "@impuesto_hidrocarburos", "name": "Imp. hidrocarburos"},
                    {"entity": "@alquiler_contador", "name": "Alquiler contador"},
                    {"entity": "@iva", "name": "IVA"},
                    {"type": "divider"},
                    {"entity": "@ajuste_lectura", "name": "Ajustar lectura del contador"},
                    {"entity": "@estado_precios", "name": "Estado de los precios"},
                ],
            },
        ],
    }

    history = {
        "type": "grid",
        "column_span": 3,
        "cards": [
            {"type": "heading", "heading": "Histórico", "icon": "mdi:chart-bar"},
            {
                "type": "custom:apexcharts-card",
                "grid_options": {"columns": "full"},
                "header": {"show": True, "title": "Últimos 30 días", "show_states": False},
                "graph_span": "30d",
                "span": {"end": "day"},
                "apex_config": {
                    "chart": {"height": 300},
                    "plotOptions": {"bar": {"borderRadius": 4}},
                    "legend": {"show": True},
                    "tooltip": {"shared": True},
                },
                "yaxis": _dual_axes(2),
                "series": [
                    {
                        "entity": "@lectura",
                        "name": "Consumo",
                        "type": "column",
                        "color": "#ff8a00",
                        "yaxis_id": "m3",
                        "unit": "m³",
                        "statistics": {"type": "change", "period": "day", "align": "start"},
                    },
                    _chart_cost_series("day", "1"),
                ],
            },
            {
                "type": "custom:apexcharts-card",
                "grid_options": {"columns": 6},
                "header": {"show": True, "title": "Hoy por horas", "show_states": False},
                "graph_span": "24h",
                "span": {"start": "day"},
                "apex_config": {"chart": {"height": 240}, "plotOptions": {"bar": {"borderRadius": 3}}},
                "series": [
                    {
                        "entity": "@lectura",
                        "name": "Consumo",
                        "type": "column",
                        "color": "#ff8a00",
                        "unit": "m³",
                        "float_precision": 2,
                        "statistics": {"type": "change", "period": "hour", "align": "start"},
                    }
                ],
            },
            {
                "type": "custom:apexcharts-card",
                "grid_options": {"columns": 6},
                "header": {"show": True, "title": "Caudal (24 h)", "show_states": True, "colorize_states": True},
                "graph_span": "24h",
                "apex_config": {"chart": {"height": 240}},
                "series": [
                    {
                        "entity": "@caudal",
                        "name": "Caudal",
                        "type": "area",
                        "curve": "stepline",
                        "color": "#03a9f4",
                        "unit": "m³/h",
                        "float_precision": 2,
                        "group_by": {"func": "avg", "duration": "10min"},
                    }
                ],
            },
            {
                "type": "custom:apexcharts-card",
                "grid_options": {"columns": "full"},
                "header": {"show": True, "title": "Últimos 12 meses", "show_states": False},
                "graph_span": "365d",
                "span": {"end": "month"},
                "apex_config": {
                    "chart": {"height": 300},
                    "plotOptions": {"bar": {"borderRadius": 4}},
                    "legend": {"show": True},
                },
                "yaxis": _dual_axes(0),
                "series": [
                    {
                        "entity": "@lectura",
                        "name": "Consumo",
                        "type": "column",
                        "color": "#ff8a00",
                        "yaxis_id": "m3",
                        "unit": "m³",
                        "statistics": {"type": "change", "period": "month", "align": "start"},
                    },
                    _chart_cost_series("month", "30.4"),
                ],
            },
        ],
    }

    view = {
        "title": title,
        "path": "gas",
        "icon": "mdi:fire",
        "type": "sections",
        "max_columns": 3,
        "sections": [today, bill, prices, history],
    }
    return {"title": title, "views": [_fill(view, ids)]}
