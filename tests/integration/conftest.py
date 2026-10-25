from __future__ import annotations

import copy
from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.syr_local.const import DOMAIN
from custom_components.syr_local.models import SyrLocalState, parse_state
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.util import dt as dt_util

SERIAL = "204033438"


def make_payload(**meta: Any) -> dict[str, Any]:
    now = dt_util.utcnow().isoformat()
    payload = {
        "schema_version": 1,
        "generated_at": now,
        "device": {
            "serial": SERIAL,
            "manufacturer": "SYR",
            "model": "LEXplus10S",
            "firmware": "SLPS 2.0",
            "type": "80",
            "mac": "0c:73:eb:50:ce:c9",
            "ip": "192.168.178.130",
        },
        "values": {
            "salt_weeks": 5,
            "salt_kg": 8.0,
            "flow_lph": 0.0,
            "remaining_capacity_l": 1215,
            "total_water_l": 583939,
            "regeneration_running": False,
            "resin_percent": 60,
            "pressure_bar": 4.8,
            "last_regeneration": "2026-01-02T03:45:17+00:00",
            "regeneration_count": 391,
            "status": None,
            "alarm": None,
        },
        "meta": {"started_at": now, "last_seen": now, "last_read": now, "request_count": 42},
    }
    payload["meta"].update(meta)
    return copy.deepcopy(payload)


def make_state(**meta: Any) -> SyrLocalState:
    return parse_state(make_payload(**meta))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    return


@pytest.fixture
def mock_get_state() -> Generator[AsyncMock]:
    with patch(
        "custom_components.syr_local.api.SyrLocalClient.async_get_state",
        new_callable=AsyncMock,
        return_value=make_state(),
    ) as mock:
        yield mock


@pytest.fixture
def config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="SYR LEXplus10S",
        unique_id=SERIAL,
        data={CONF_HOST: "local-syr-local", CONF_PORT: 8099},
    )
