from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.syr_local.api import CannotConnectError
from custom_components.syr_local.const import DOMAIN
from custom_components.syr_local.models import (
    InvalidStateError,
    UnsupportedVersionError,
    parse_state,
)
from homeassistant.config_entries import SOURCE_HASSIO, SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.hassio import HassioServiceInfo

from .conftest import SERIAL, make_payload

USER_INPUT = {CONF_HOST: "local-syr-local", CONF_PORT: 8099}


def discovery(**config) -> HassioServiceInfo:
    return HassioServiceInfo(
        config={"host": "local-syr-local", "port": 8099, "serial": SERIAL, **config},
        name="SYR Local",
        slug="syr_local",
        uuid="1234",
    )


async def test_user_flow(hass: HomeAssistant, mock_get_state: AsyncMock) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: " local-syr-local ", CONF_PORT: 8099}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "SYR LEXplus10S"
    assert result["data"] == USER_INPUT
    assert result["result"].unique_id == SERIAL


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [
        (CannotConnectError("x"), "cannot_connect"),
        (InvalidStateError("x"), "invalid_response"),
        (UnsupportedVersionError("x"), "unsupported_version"),
    ],
)
async def test_user_flow_errors_recover(
    hass: HomeAssistant, mock_get_state: AsyncMock, side_effect: Exception, error: str
) -> None:
    good = mock_get_state.return_value
    mock_get_state.side_effect = side_effect
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    mock_get_state.side_effect = None
    mock_get_state.return_value = good
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_no_device(hass: HomeAssistant, mock_get_state: AsyncMock) -> None:
    payload = make_payload()
    payload["device"]["serial"] = None
    mock_get_state.return_value = parse_state(payload)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["errors"] == {"base": "no_device"}


async def test_user_flow_already_configured_updates_host(
    hass: HomeAssistant, mock_get_state: AsyncMock, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.178.10", CONF_PORT: 8100}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert config_entry.data == {CONF_HOST: "192.168.178.10", CONF_PORT: 8100}


async def test_hassio_discovery(hass: HomeAssistant, mock_get_state: AsyncMock) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_HASSIO}, data=discovery()
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "hassio_confirm"
    assert result["description_placeholders"] == {"name": "SYR LEXplus10S", "serial": SERIAL}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == USER_INPUT
    assert result["result"].unique_id == SERIAL


@pytest.mark.parametrize(
    "config", [{"host": ""}, {"host": 5}, {"port": "8099"}, {"port": 0}, {"port": True}]
)
async def test_hassio_invalid_discovery(
    hass: HomeAssistant, mock_get_state: AsyncMock, config: dict
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_HASSIO}, data=discovery(**config)
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "invalid_discovery_info"
    mock_get_state.assert_not_called()


async def test_hassio_already_configured_updates_host(
    hass: HomeAssistant, mock_get_state: AsyncMock, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_HASSIO}, data=discovery(host="a0d7b954-syr-local")
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert config_entry.data[CONF_HOST] == "a0d7b954-syr-local"


async def test_hassio_cannot_connect(hass: HomeAssistant, mock_get_state: AsyncMock) -> None:
    mock_get_state.side_effect = CannotConnectError("x")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_HASSIO}, data=discovery()
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_reconfigure(
    hass: HomeAssistant, mock_get_state: AsyncMock, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "fd00::10", CONF_PORT: 8099}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data == {CONF_HOST: "fd00::10", CONF_PORT: 8099}
    await hass.async_block_till_done()


async def test_reconfigure_wrong_device(
    hass: HomeAssistant, mock_get_state: AsyncMock, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    payload = make_payload()
    payload["device"]["serial"] = "999999999"
    mock_get_state.return_value = parse_state(payload)
    result = await config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"
    assert config_entry.data == USER_INPUT
