from datetime import UTC
from zoneinfo import ZoneInfo

from server.mapping import VALUE_KEYS, Identity, device_identity, semantic_values

from .fixtures import FULL_VALUES

EXPECTED_VALUES = {
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
}


def test_semantic_values_fixture():
    values = semantic_values(FULL_VALUES, UTC)
    assert values == EXPECTED_VALUES
    assert list(values) == list(VALUE_KEYS)
    for key in ("salt_weeks", "remaining_capacity_l", "total_water_l", "resin_percent"):
        assert type(values[key]) is int
    for key in ("salt_kg", "flow_lph", "pressure_bar"):
        assert type(values[key]) is float


def test_semantic_values_empty_before_contact():
    assert semantic_values({}) == {}


def test_omits_unusable_values():
    raw = {
        "getSS1": "",
        "getSV1": "abc",
        "getFLO": "-1",
        "getCOF": "nan",
        "getRG1": "2",
        "getPRS": "255",
        "getLAR": "0",
        "getTOR": "1.5",
    }
    assert semantic_values(raw) == {}


def test_status_and_alarm_text():
    values = semantic_values({"getSTA": "Bitte Salz nachfüllen", "getALM": " A1 "})
    assert values == {"status": "Bitte Salz nachfüllen", "alarm": "A1"}


def test_regeneration_running_true():
    assert semantic_values({"getRG1": "1"}) == {"regeneration_running": True}


def test_last_regeneration_is_local_wall_time():
    # 1767325517 is 2026-01-02 03:45:17 on the device clock; in Berlin (CET, UTC+1)
    # that is 02:45:17 UTC.
    values = semantic_values({"getLAR": "1767325517"}, ZoneInfo("Europe/Berlin"))
    assert values == {"last_regeneration": "2026-01-02T02:45:17+00:00"}


def test_dgw_is_not_used_as_a_value():
    assert semantic_values({"getDGW": "192.168.178.1"}) == {}


def test_device_identity():
    assert device_identity(FULL_VALUES, "192.168.178.130", Identity()) == {
        "serial": "204033438",
        "manufacturer": "SYR",
        "model": "LEXplus10S",
        "firmware": "SLPS 2.0",
        "type": "80",
        "mac": "0c:73:eb:50:ce:c9",
        "ip": "192.168.178.130",
    }


def test_device_identity_before_contact_uses_persisted_identity():
    identity = device_identity({}, None, Identity(serial="204033438", model="LEXplus10S"))
    assert identity == {
        "serial": "204033438",
        "manufacturer": "SYR",
        "model": "LEXplus10S",
        "firmware": None,
        "type": None,
        "mac": None,
        "ip": None,
    }


def test_device_identity_rejects_unsafe_serial_and_mac():
    identity = device_identity({"getSRN": "../../x", "getMAC": "zz"}, "10.0.0.5", Identity())
    assert identity["serial"] is None
    assert identity["mac"] is None
    assert identity["ip"] == "10.0.0.5"
