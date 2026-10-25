import json
from datetime import UTC, datetime, timedelta

from server.mapping import Identity
from server.state import DeviceState, state_document

from .fixtures import FULL_VALUES

T0 = datetime(2026, 10, 25, 14, 0, tzinfo=UTC)


def test_document_before_device_contact():
    state = DeviceState(T0, Identity())
    document = state_document(state.snapshot(), T0, UTC)
    assert document == {
        "schema_version": 1,
        "generated_at": "2026-10-25T14:00:00+00:00",
        "device": {
            "serial": None,
            "manufacturer": "SYR",
            "model": None,
            "firmware": None,
            "type": None,
            "mac": None,
            "ip": None,
        },
        "values": {},
        "meta": {
            "started_at": "2026-10-25T14:00:00+00:00",
            "last_seen": None,
            "last_read": None,
            "request_count": 0,
        },
    }


def test_record_identity_then_readings():
    state = DeviceState(T0, Identity())
    basic = {key: FULL_VALUES[key] for key in ("getSRN", "getVER", "getFIR", "getTYP", "getCNA")}
    changed = state.record(basic, "192.168.178.130", T0 + timedelta(seconds=1))
    assert changed == Identity(serial="204033438", model="LEXplus10S")
    assert state.record(basic, "192.168.178.130", T0 + timedelta(seconds=12)) is None

    snapshot = state.snapshot()
    assert snapshot.last_read is None
    assert snapshot.request_count == 2

    state.record(FULL_VALUES, "192.168.178.130", T0 + timedelta(seconds=23))
    document = state_document(state.snapshot(), T0 + timedelta(seconds=30), UTC)
    assert document["device"]["serial"] == "204033438"
    assert document["values"]["total_water_l"] == 583939
    assert document["meta"] == {
        "started_at": "2026-10-25T14:00:00+00:00",
        "last_seen": "2026-10-25T14:00:23+00:00",
        "last_read": "2026-10-25T14:00:23+00:00",
        "request_count": 3,
    }
    # JSON-serialisable without custom encoders.
    json.dumps(document)


def test_empty_request_counts_as_seen():
    state = DeviceState(T0, Identity(serial="204033438", model="LEXplus10S"))
    assert state.record({}, "192.168.178.130", T0) is None
    assert state.snapshot().last_seen == T0


def test_empty_reading_does_not_count_as_read():
    state = DeviceState(T0, Identity())
    state.record({"getSS1": ""}, "192.168.178.130", T0)
    assert state.snapshot().last_seen == T0
    assert state.snapshot().last_read is None


def test_cleared_alarm_is_reported_as_null():
    state = DeviceState(T0, Identity())
    state.record({"getALM": "A1"}, "10.0.0.2", T0)
    state.record({"getALM": ""}, "10.0.0.2", T0)
    assert state_document(state.snapshot(), T0, UTC)["values"] == {"alarm": None}
