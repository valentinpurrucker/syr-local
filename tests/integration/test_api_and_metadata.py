import json
from pathlib import Path

import aiohttp
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.syr_local.api import CannotConnectError, SyrLocalClient, state_url
from custom_components.syr_local.binary_sensor import BINARY_SENSORS
from custom_components.syr_local.models import VALUE_TYPES, InvalidStateError, UnsupportedVersionError
from custom_components.syr_local.sensor import SENSORS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .conftest import make_payload

INTEGRATION = Path(__file__).resolve().parents[2] / "custom_components" / "syr_local"
URL = "http://local-syr-local:8099/api/v1/state"


def test_state_url_handles_ipv6():
    assert str(state_url("fd00::1", 8099)) == "http://[fd00::1]:8099/api/v1/state"
    assert str(state_url("local-syr-local", 8099)) == URL


async def test_client_success(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(URL, json=make_payload())
    client = SyrLocalClient(async_get_clientsession(hass), "local-syr-local", 8099)
    state = await client.async_get_state()
    assert state.device.serial == "204033438"
    assert aioclient_mock.mock_calls[0][0] == "GET"


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"exc": aiohttp.ClientConnectionError()}, CannotConnectError),
        ({"exc": TimeoutError()}, CannotConnectError),
        ({"status": 500}, InvalidStateError),
        ({"text": "<html>"}, InvalidStateError),
        ({"json": {**make_payload(), "schema_version": 2}}, UnsupportedVersionError),
        ({"json": {"schema_version": 1}}, InvalidStateError),
    ],
)
async def test_client_errors(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, kwargs: dict, error: type
) -> None:
    aioclient_mock.get(URL, **kwargs)
    client = SyrLocalClient(async_get_clientsession(hass), "local-syr-local", 8099)
    with pytest.raises(error):
        await client.async_get_state()


def test_entities_cover_contract():
    keys = [d.key for d in SENSORS] + [d.key for d in BINARY_SENSORS]
    assert len(keys) == len(set(keys))
    assert set(keys) == set(VALUE_TYPES)


def test_translations():
    strings = json.loads((INTEGRATION / "strings.json").read_text())
    assert strings == json.loads((INTEGRATION / "translations" / "en.json").read_text())
    for description in SENSORS:
        assert description.translation_key in strings["entity"]["sensor"]
    for description in BINARY_SENSORS:
        assert description.translation_key in strings["entity"]["binary_sensor"]


def test_manifest():
    manifest = json.loads((INTEGRATION / "manifest.json").read_text())
    assert manifest["domain"] == "syr_local"
    assert manifest["config_flow"] is True
    assert manifest["integration_type"] == "device"
    assert manifest["iot_class"] == "local_polling"
    assert manifest["requirements"] == []
    assert manifest["version"] == "0.1.0"
    assert manifest["codeowners"]
    assert "OWNER" not in manifest["documentation"]


def test_hacs_minimum_version():
    hacs = json.loads((INTEGRATION.parents[1] / "hacs.json").read_text())
    assert hacs["homeassistant"] == "2026.10.0"
    assert hacs["content_in_root"] is False
