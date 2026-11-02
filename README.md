# Gas TUR

**Contador de gas por pulsos, precios de la tarifa regulada TUR y factura al céntimo, para Home Assistant.**

*Counts the pulses of a gas meter (reed switch on a Zigbee/ESPHome door sensor), keeps the
reading, reads the Spanish regulated gas tariff (TUR 1/2/3) and estimates the bill exactly as the
retailer computes it. Creates its own dashboard.*

Con un sensor de puerta con reed pegado al contador y esta integración tienes:

- La **lectura del contador** lista para el panel de Energía, sin counters, automatizaciones ni YAML.
- Los **precios TUR** leídos solos de la Comercializadora Regulada cada 6 horas, con historial.
  El impuesto de hidrocarburos también se actualiza solo.
- La **factura en curso** calculada como la real: m³ enteros, kWh redondeados y, si la TUR
  cambia a mitad de periodo, término fijo y consumo repartidos por días.
- Un **panel "Gas"** en la barra lateral, con el gasto de hoy, la factura, los precios y las gráficas.

## Instalación

[![Abrir en HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=manu8613&repository=gas-tur&category=integration)

1. **HACS → ⋮ → Repositorios personalizados**, añade `https://github.com/manu8613/gas-tur`
   con categoría **Integración** e instala **Gas TUR**.
2. Reinicia Home Assistant.
3. **Ajustes → Dispositivos y servicios → Añadir integración → Gas TUR**.

El asistente pide dos cosas:

| Paso | Qué poner |
|---|---|
| Contador | El sensor binario del reed, cuándo cuenta el pulso (de encendido a apagado normalmente), m³ por pulso (en la placa: `1 imp = 0,01 m³`), la tarifa y la **lectura actual** del contador. |
| Última factura | Fecha y lectura de la "Lectura actual" de tu última factura, el factor de conversión (`1 m³ = … kWh`) y el alquiler del contador (€/día). |

El panel usa **Mushroom**, **ApexCharts card** y **card-mod** (HACS → Frontend). Sin ellos, las
tarjetas de esas extensiones salen con error; el resto de la integración funciona igual.

### Panel de Energía

En **Ajustes → Paneles → Energía → Consumo de gas** elige **Lectura del contador** y, como
precio, **Utilizar una entidad con el precio actual → Precio por m³**.

## Cada vez que llega una factura

En el panel, tarjeta **Cerrar factura**, pon la fecha de la lectura, la lectura y el factor de
conversión de esa factura. También vale la acción `gas_tur.nueva_factura`:

```yaml
action: gas_tur.nueva_factura
data:
  fecha: "2026-10-21"
  lectura: 22814
  factor_conversion: 10.318
```

## Entidades

| Entidad | Para qué |
|---|---|
| Lectura del contador (m³) | Total del contador; va al panel de Energía. |
| Gas hoy / este mes / desde la última factura (m³) | Consumos parciales. |
| Caudal (m³/h) | Calculado del tiempo entre pulsos; cae a 0 tras 15 min sin pulsos. |
| Último pulso | Hora del último pulso. |
| Precio energía TUR (€/kWh), Término fijo TUR (€/mes) | Precios sin impuestos; el historial va en los atributos. |
| Precio por m³ | Con impuesto de hidrocarburos e IVA; es el precio para Energía. |
| Coste fijo diario | Término fijo + alquiler con IVA. |
| Coste hoy / este mes (€) | Consumo × precio + parte fija. |
| Factura en curso (€) | Total hasta hoy; las líneas de la factura van en los atributos. |
| Previsión de factura (€) | A este ritmo, para un periodo completo (61 días por defecto). |
| Estado de los precios | `ok`, `error`, `manual` o `pendiente`. |
| Números editables | Factor de conversión, lectura de la factura, impuesto de hidrocarburos, alquiler, IVA y ajuste de la lectura. |
| Fecha de la última factura | Editable. |

## Acciones

| Acción | Qué hace |
|---|---|
| `gas_tur.nueva_factura` | Empieza un periodo con la fecha, lectura y factor de la última factura. |
| `gas_tur.ajustar_lectura` | Pone la lectura que marca el contador sin tocar el consumo de hoy ni del mes. |
| `gas_tur.establecer_precio` | Añade o corrige un precio TUR desde una fecha (sin impuestos). |
| `gas_tur.actualizar_precios` | Lee los precios ahora. |
| `gas_tur.crear_panel` | Vuelve a generar el panel. |

Si el contador baja (por ejemplo, al ajustar la lectura a la baja), el panel de Energía lo toma
como un reinicio. Se corrige en **Herramientas → Estadísticas → ajustar suma**.

## Cómo calcula la factura

Reproduce la factura de la comercializadora de referencia:

1. Días: del día siguiente a la lectura anterior hasta hoy.
2. m³: lectura actual entera − lectura de la factura.
3. kWh: m³ × factor de conversión, redondeado.
4. Si el precio TUR cambia dentro del periodo, el término fijo se cobra por días a cada precio y
   los kWh se reparten en proporción a los días.
5. Impuesto de hidrocarburos sobre todos los kWh, alquiler por días, cada línea redondeada a
   céntimos, e IVA sobre la base.

Con la factura del 21/10/2026 (24/08 → 21/10, 37 m³, 10,318 kWh/m³, cambio de precio el 1/10)
sale **41,77 €**, igual que la real. Está en las pruebas.

Los precios de días anteriores a la instalación no se conocen: si tu periodo empezó antes de un
cambio de TUR, añade el precio anterior con `gas_tur.establecer_precio`.

## Panel

El panel se genera desde las entidades reales en `/config/gas_tur/panel_<id>.yaml` y se registra
en `/gas-tur`. Se regenera cada vez que carga la integración, así que no se edita desde la
interfaz: si quieres personalizarlo, copia ese YAML a un panel tuyo y desactiva
"Crear el panel de gas" en las opciones. Si ya existe un panel en `/gas-tur`, no lo toca.

## Desarrollo

```bash
pip install -r requirements_test.txt
pytest
```

`tests/test_tariff.py` y `tests/test_panel.py` corren solo con Python; `tests/test_init.py`
arranca un Home Assistant de pruebas.

Precios: [Comercializadora Regulada](https://www.comercializadoraregulada.es/regulada/gas/tur_2).
Sin relación con ninguna comercializadora.
