from datetime import timedelta
from unittest.mock import AsyncMock

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.syr_local.api import CannotConnectError
from custom_components.syr_local.const import DOMAIN
from custom_components.syr_local.diagnostics import async_get_config_entry_diagnostics
from custom_components.syr_local.models import parse_state
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util

from .conftest import SERIAL, make_payload, make_state


def entity_id(hass: HomeAssistant, platform: str, key: str) -> str:
    found = er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{SERIAL}_{key}")
    assert found, key
    return found


async def setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_creates_read_only_entities(
    hass: HomeAssistant, mock_get_state: AsyncMock, config_entry: MockConfigEntry
) -> None:
    await setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    expected = {
        "salt_weeks": ("5", "w"),
        "salt_kg": ("8.0", "kg"),
        "flow_lph": ("0.0", "L/h"),
        "remaining_capacity_l": ("1215", "L"),
        "total_water_l": ("583939", "L"),
        "resin_percent": ("60", "%"),
        "last_regeneration": ("2026-01-02T03:45:17+00:00", None),
    }
    for key, (value, unit) in expected.items():
        state = hass.states.get(entity_id(hass, "sensor", key))
        assert state is not None, key
        assert state.state == value, key
        assert state.attributes.get("unit_of_measurement") == unit, key

    assert hass.states.get(entity_id(hass, "binary_sensor", "regeneration_running")).state == STATE_OFF

    registry = er.async_get(hass)
    for key in ("pressure_bar", "regeneration_count"):
        assert registry.async_get(entity_id(hass, "sensor", key)).disabled_by is er.RegistryEntryDisabler.INTEGRATION
    for key in ("status", "alarm"):
        assert registry.async_get(entity_id(hass, "sensor", key)).entity_category == "diagnostic"

    device = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, SERIAL), config_entry.entry_id)
    assert device is not None
    assert device.manufacturer == "SYR"
    assert device.model == "LEXplus10S"
    assert device.serial_number == SERIAL
    assert device.sw_version == "SLPS 2.0"
    assert (dr.CONNECTION_NETWORK_MAC, "0c:73:eb:50:ce:c9") in device.connections
    assert device.name == "SYR LEXplus10S"

    # Read-only by construction: no services, only sensor platforms.
    assert not hass.services.async_services_for_domain(DOMAIN)
    platforms = {entry.domain for entry in er.async_entries_for_config_entry(registry, config_entry.entry_id)}
    assert platforms == {"sensor", "binary_sensor"}

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_retry_when_addon_unreachable(
    hass: HomeAssistant, mock_get_state: AsyncMock, config_entry: MockConfigEntry
) -> None:
    mock_get_state.side_effect = CannotConnectError("x")
    await setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_unavailable_when_device_stale(
    hass: HomeAssistant, mock_get_state: AsyncMock, config_entry: MockConfigEntry
) -> None:
    stale = (dt_util.utcnow() - timedelta(minutes=6)).isoformat()
    mock_get_state.return_value = make_state(last_seen=stale)
    await setup(hass, config_entry)
    assert hass.states.get(entity_id(hass, "sensor", "salt_weeks")).state == STATE_UNAVAILABLE


async def test_unavailable_when_update_fails(
    hass: HomeAssistant,
    mock_get_state: AsyncMock,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    await setup(hass, config_entry)
    sensor = entity_id(hass, "sensor", "salt_weeks")
    assert hass.states.get(sensor).state == "5"

    mock_get_state.side_effect = CannotConnectError("x")
    freezer.tick(timedelta(seconds=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(sensor).state == STATE_UNAVAILABLE

    mock_get_state.side_effect = None
    mock_get_state.return_value = make_state(last_seen=dt_util.utcnow().isoformat())
    freezer.tick(timedelta(seconds=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(sensor).state == "5"


async def test_unavailable_when_addon_reports_another_device(
    hass: HomeAssistant,
    mock_get_state: AsyncMock,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    await setup(hass, config_entry)
    sensor = entity_id(hass, "sensor", "salt_weeks")
    assert hass.states.get(sensor).state == "5"

    payload = make_payload()
    payload["device"]["serial"] = "999999999"
    mock_get_state.return_value = parse_state(payload)
    freezer.tick(timedelta(seconds=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(sensor).state == STATE_UNAVAILABLE


async def test_diagnostics_are_redacted(
    hass: HomeAssistant, mock_get_state: AsyncMock, config_entry: MockConfigEntry
) -> None:
    await setup(hass, config_entry)
    diagnostics = await async_get_config_entry_diagnostics(hass, config_entry)
    assert diagnostics["addon_url"] == "http://local-syr-local:8099/api/v1/state"
    assert diagnostics["coordinator"]["last_update_success"] is True
    assert diagnostics["coordinator"]["device_online"] is True
    device = diagnostics["state"]["device"]
    assert device["serial"] == device["mac"] == device["ip"] == "**REDACTED**"
    assert diagnostics["entry"]["unique_id"] == "**REDACTED**"
    assert diagnostics["state"]["values"]["total_water_l"] == 583939
    assert SERIAL not in str(diagnostics)
    assert "0c:73:eb:50:ce:c9" not in str(diagnostics)
