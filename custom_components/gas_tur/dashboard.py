"""Create the Gas dashboard in the sidebar when the integration loads.

The dashboard is a YAML-mode Lovelace dashboard generated from the real entity
ids, so it always matches the installed entities. It is rebuilt on every load.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from homeassistant.components import frontend, persistent_notification
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.util.yaml import dump

from .const import DASHBOARD_URL, DOMAIN
from .manager import GasTurConfigEntry
from .panel import ENTITY_KEYS, build_panel

_LOGGER = logging.getLogger(__name__)

_OURS = f"{DOMAIN}_panels"


def panel_path(hass: HomeAssistant, entry_id: str) -> Path:
    return Path(hass.config.path(DOMAIN, f"panel_{entry_id}.yaml"))


def dashboard_url(hass: HomeAssistant, entry: GasTurConfigEntry) -> str:
    entries = sorted(hass.config_entries.async_entries(DOMAIN), key=lambda e: e.entry_id)
    index = next((i for i, e in enumerate(entries) if e.entry_id == entry.entry_id), 0)
    return DASHBOARD_URL if index == 0 else f"{DASHBOARD_URL}-{index + 1}"


def _entity_ids(hass: HomeAssistant, entry: GasTurConfigEntry) -> dict[str, str]:
    registry = er.async_get(hass)
    ids: dict[str, str] = {}
    for key, platform in ENTITY_KEYS.items():
        entity_id = registry.async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}")
        ids[key] = entity_id or f"{platform}.{DOMAIN}_{key}"
    return ids


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _dashboards(hass: HomeAssistant) -> dict[str | None, Any] | None:
    data = hass.data.get("lovelace")
    if data is None:
        return None
    return data.dashboards if hasattr(data, "dashboards") else data["dashboards"]


async def async_setup_dashboard(hass: HomeAssistant, entry: GasTurConfigEntry) -> None:
    """Write the dashboard YAML and register it in the sidebar."""
    url = dashboard_url(hass, entry)
    path = panel_path(hass, entry.entry_id)
    config = build_panel(_entity_ids(hass, entry), entry.title)
    await hass.async_add_executor_job(_write, path, dump(config))

    ours: set[str] = hass.data.setdefault(_OURS, set())
    dashboards = _dashboards(hass)
    if dashboards is None:
        _LOGGER.warning("Lovelace no está cargado; el panel está en %s", path)
        return
    if url not in ours and (url in dashboards or frontend.async_panel_exists(hass, url)):
        _notify(hass, entry, url, path)
        return

    try:
        from homeassistant.components.lovelace.dashboard import LovelaceYAML

        dashboards[url] = LovelaceYAML(
            hass,
            url,
            {
                "mode": "yaml",
                "filename": str(path.relative_to(hass.config.config_dir)),
                "title": entry.title,
                "icon": "mdi:fire",
                "show_in_sidebar": True,
                "require_admin": False,
            },
        )
        frontend.async_register_built_in_panel(
            hass,
            "lovelace",
            sidebar_title=entry.title,
            sidebar_icon="mdi:fire",
            frontend_url_path=url,
            config={"mode": "yaml"},
            require_admin=False,
            update=frontend.async_panel_exists(hass, url),
        )
    except Exception:  # noqa: BLE001 - never break the integration for the dashboard
        _LOGGER.exception("No se pudo registrar el panel de gas; el YAML está en %s", path)
        _notify(hass, entry, url, path)
        return
    ours.add(url)


@callback
def async_remove_dashboard(hass: HomeAssistant, entry: GasTurConfigEntry) -> None:
    """Take the dashboard out of the sidebar (the YAML file stays)."""
    url = dashboard_url(hass, entry)
    ours: set[str] = hass.data.get(_OURS, set())
    if url not in ours:
        return
    ours.discard(url)
    try:
        frontend.async_remove_panel(hass, url, warn_if_unknown=False)
    except TypeError:  # Home Assistant before warn_if_unknown existed
        frontend.async_remove_panel(hass, url)
    if (dashboards := _dashboards(hass)) is not None:
        dashboards.pop(url, None)


@callback
def _notify(hass: HomeAssistant, entry: GasTurConfigEntry, url: str, path: Path) -> None:
    persistent_notification.async_create(
        hass,
        (
            f"Ya existe un panel en `/{url}`, así que no lo he sustituido. "
            f"El panel de **{entry.title}** está en `{path}`: cópialo en un panel nuevo "
            "(Editar → Editor de configuración en bruto) o borra el existente y ejecuta "
            "la acción `gas_tur.crear_panel`."
        ),
        title="Gas TUR",
        notification_id=f"{DOMAIN}_{entry.entry_id}_panel",
    )
