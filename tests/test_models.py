"""Pure tests of the integration's payload parsing (no Home Assistant needed)."""

import copy
from datetime import UTC, datetime

import pytest

from tests.conftest import load_integration_models

models = load_integration_models()

PAYLOAD = {
    "schema_version": 1,
    "generated_at": "2026-10-25T14:00:00+00:00",
    "device": {
        "serial": "204033438",
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
        "future_value": 1,
    },
    "meta": {
        "started_at": "2026-10-25T13:00:00+00:00",
        "last_seen": "2026-10-25T13:59:50+00:00",
        "last_read": "2026-10-25T13:59:00+00:00",
        "request_count": 42,
    },
}


def test_parse_valid_payload():
    state = models.parse_state(PAYLOAD)
    assert state.device == models.DeviceInfo(
        serial="204033438", manufacturer="SYR", model="LEXplus10S",
        firmware="SLPS 2.0", mac="0c:73:eb:50:ce:c9", ip="192.168.178.130",
    )
    assert state.values["total_water_l"] == 583939
    assert state.values["last_regeneration"] == datetime(2026, 1, 2, 3, 45, 17, tzinfo=UTC)
    assert state.values["status"] is None
    assert "future_value" not in state.values
    assert state.last_seen == datetime(2026, 10, 25, 13, 59, 50, tzinfo=UTC)
    assert state.request_count == 42


@pytest.mark.parametrize("version", [None, 0, 2, "1", True])
def test_rejects_other_schema_versions(version):
    payload = {**PAYLOAD, "schema_version": version}
    with pytest.raises(models.UnsupportedVersionError):
        models.parse_state(payload)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.pop("device"),
        lambda p: p.__setitem__("values", []),
        lambda p: p["meta"].__setitem__("request_count", "42"),
        lambda p: p["meta"].__setitem__("last_seen", "yesterday"),
        lambda p: p["meta"].__setitem__("last_seen", "2026-10-25T13:59:50"),
        lambda p: p["device"].__setitem__("serial", 204033438),
    ],
)
def test_rejects_malformed_payloads(mutate):
    payload = copy.deepcopy(PAYLOAD)
    mutate(payload)
    with pytest.raises(models.InvalidStateError):
        models.parse_state(payload)


def test_rejects_non_object():
    with pytest.raises(models.InvalidStateError):
        models.parse_state([])


def test_drops_values_with_wrong_type():
    payload = copy.deepcopy(PAYLOAD)
    payload["values"].update(
        salt_weeks="5", regeneration_running=1, total_water_l=True,
        last_regeneration="not a time", status=3,
    )
    values = models.parse_state(payload).values
    for key in ("salt_weeks", "regeneration_running", "total_water_l", "last_regeneration", "status"):
        assert key not in values
