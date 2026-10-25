import json

import pytest


def test_state_contract(running):
    status, body = running.api("GET", "/api/v1/state")
    assert status == 200
    document = json.loads(body)
    assert document["schema_version"] == 1
    assert set(document) == {"schema_version", "generated_at", "device", "values", "meta"}
    assert set(document["device"]) == {"serial", "manufacturer", "model", "firmware", "type", "mac", "ip"}
    assert document["values"] == {}
    assert set(document["meta"]) == {"started_at", "last_seen", "last_read", "request_count"}


def test_health(running):
    status, body = running.api("GET", "/health")
    assert status == 200
    assert json.loads(body) == {"status": "ok"}


@pytest.mark.parametrize("path", ["/", "/state.json", "/api/v1/raw", "/api/v2/state", "/api/v1/state/x"])
def test_other_paths_404(running, path):
    assert running.api("GET", path)[0] == 404


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_other_methods_404(running, method):
    assert running.api(method, "/api/v1/state")[0] == 404
