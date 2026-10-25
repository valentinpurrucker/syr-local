"""Read-only binary sensors for SYR Local."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SyrLocalConfigEntry
from .entity import SyrLocalEntity

PARALLEL_UPDATES = 0

BINARY_SENSORS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key="regeneration_running",
        translation_key="regeneration_running",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SyrLocalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        SyrLocalBinarySensor(coordinator, description) for description in BINARY_SENSORS
    )


class SyrLocalBinarySensor(SyrLocalEntity, BinarySensorEntity):
    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.values.get(self.entity_description.key)
