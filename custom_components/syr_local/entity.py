"""Shared entity base for SYR Local."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SyrLocalCoordinator


class SyrLocalEntity(CoordinatorEntity[SyrLocalCoordinator]):
    """A read-only entity backed by the add-on state."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: SyrLocalCoordinator, description: EntityDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        # The config entry's unique ID is the device serial.
        serial = coordinator.config_entry.unique_id or ""
        device = coordinator.data.device
        self._attr_unique_id = f"{serial}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            connections={(CONNECTION_NETWORK_MAC, device.mac)} if device.mac else set(),
            manufacturer=device.manufacturer or "SYR",
            model=device.model,
            name=f"SYR {device.model}" if device.model else "SYR water softener",
            serial_number=serial,
            sw_version=device.firmware,
        )

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.device_online
