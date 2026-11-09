# CLAUDE.md — Gas TUR

## Qué es
Integración HACS pública (`custom_components/gas_tur`): contador de gas por pulsos (reed), precios de la tarifa regulada TUR y factura estimada, con panel.

## Por dónde empezar
1. `CHANGELOG.md` y `docs/STATUS.md` si existe.
2. Solo el módulo afectado (`tariff.py` precios, `manager.py` lógica, `sensor.py` entidades, `dashboard.py`/`panel.py` panel).

## Reglas
- Público y anónimo; autor manu8613.
- Versión en `manifest.json` + `## [X.Y.Z]` en CHANGELOG → `release.yml` crea etiqueta y release (HACS permite volver atrás).
- Pruebas: `pip install -r requirements_test.txt && pytest -q`. Si falla CI, arreglar en rama, no con commits de prueba en main.
- Centro de Control lo detecta: no romper nombres de entidades públicas.
- Cambios en rama y por PR. Nada de merge sin autorización.
- Al terminar: bloque CIERRE.
