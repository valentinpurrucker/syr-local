"""Read-only sensors for SYR Local."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfMass,
    UnitOfPressure,
    UnitOfTime,
    UnitOfVolume,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SyrLocalConfigEntry
from .entity import SyrLocalEntity

PARALLEL_UPDATES = 0

# Each key is a semantic value key of the add-on state document.
SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="salt_weeks",
        translation_key="salt_weeks",
        native_unit_of_measurement=UnitOfTime.WEEKS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="salt_kg",
        translation_key="salt_kg",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="flow_lph",
        translation_key="flow_lph",
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        native_unit_of_measurement=UnitOfVolumeFlowRate.LITERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="remaining_capacity_l",
        translation_key="remaining_capacity_l",
        device_class=SensorDeviceClass.VOLUME_STORAGE,
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="total_water_l",
        translation_key="total_water_l",
        device_class=SensorDeviceClass.WATER,
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="resin_percent",
        translation_key="resin_percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="pressure_bar",
        translation_key="pressure_bar",
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.BAR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="last_regeneration",
        translation_key="last_regeneration",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="regeneration_count",
        translation_key="regeneration_count",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="status",
        translation_key="status",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="alarm",
        translation_key="alarm",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SyrLocalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(SyrLocalSensor(coordinator, description) for description in SENSORS)


class SyrLocalSensor(SyrLocalEntity, SensorEntity):
    @property
    def native_value(self) -> float | int | str | datetime | None:
        return self.coordinator.data.values.get(self.entity_description.key)
