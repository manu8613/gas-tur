"""Base entity for Gas TUR."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .manager import GasTurManager


class GasTurEntity(CoordinatorEntity[GasTurManager]):
    """Entity attached to the gas meter device."""

    _attr_has_entity_name = True

    def __init__(self, manager: GasTurManager, key: str) -> None:
        super().__init__(manager)
        entry = manager.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Gas TUR",
            model=f"Contador de gas · TUR {manager.tariff[-1]}",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://github.com/manu8613/gas-tur",
        )
