"""The add-on and the integration must agree on the state contract."""

import json
from datetime import UTC, datetime, timedelta

from server import __version__ as addon_package_version
from server.mapping import SCHEMA_VERSION, VALUE_KEYS, Identity
from server.state import DeviceState, state_document

from tests.addon.fixtures import FULL_VALUES
from tests.conftest import REPO, load_integration_models

models = load_integration_models()


def test_schema_version_and_keys_match():
    assert models.SCHEMA_VERSION == SCHEMA_VERSION == 1
    assert set(models.VALUE_TYPES) == set(VALUE_KEYS)


def test_versions_match():
    manifest = json.loads((REPO / "custom_components/syr_local/manifest.json").read_text())
    config = (REPO / "syr_local/config.yaml").read_text()
    assert f'version: "{manifest["version"]}"' in config
    assert addon_package_version == manifest["version"]


def test_integration_parses_addon_output():
    t0 = datetime(2026, 10, 25, 14, 0, tzinfo=UTC)
    store = DeviceState(t0, Identity())
    store.record(FULL_VALUES, "192.168.178.130", t0 + timedelta(seconds=5))
    payload = json.loads(json.dumps(state_document(store.snapshot(), t0 + timedelta(seconds=6), UTC)))

    state = models.parse_state(payload)
    assert state.device.serial == "204033438"
    assert state.device.model == "LEXplus10S"
    assert state.device.firmware == "SLPS 2.0"
    assert state.device.mac == "0c:73:eb:50:ce:c9"
    assert state.last_seen == t0 + timedelta(seconds=5)
    assert state.request_count == 1
    assert set(state.values) == set(VALUE_KEYS)
    assert state.values["last_regeneration"] == datetime(2026, 1, 2, 3, 45, 17, tzinfo=UTC)
    assert state.values["regeneration_running"] is False


def test_integration_parses_empty_addon_state():
    t0 = datetime(2026, 10, 25, 14, 0, tzinfo=UTC)
    payload = json.loads(json.dumps(state_document(DeviceState(t0, Identity()).snapshot(), t0, UTC)))
    state = models.parse_state(payload)
    assert state.device.serial is None
    assert dict(state.values) == {}
    assert state.last_seen is None
