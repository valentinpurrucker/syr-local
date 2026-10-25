import ipaddress
import json

import pytest

from server.config import Config, ConfigError, load_config
from server.mapping import Identity
from server.storage import load_identity, save_identity


def env(path):
    return {"SYR_LOCAL_DATA_DIR": str(path)}


def test_defaults_without_options_file(tmp_path):
    config = load_config(env(tmp_path))
    assert config == Config(data_dir=tmp_path)
    assert config.is_allowed("1.2.3.4")


def test_options_file(tmp_path):
    (tmp_path / "options.json").write_text(json.dumps({
        "poll_interval": 120,
        "allowed_device_ips": ["192.168.178.130", "10.0.0.0/24"],
        "log_level": "debug",
        "log_requests": True,
    }))
    config = load_config(env(tmp_path))
    assert config.poll_interval == 120
    assert config.allowed_device_ips == (
        ipaddress.ip_network("192.168.178.130/32"),
        ipaddress.ip_network("10.0.0.0/24"),
    )
    assert config.log_level == "debug" and config.log_requests is True
    assert config.is_allowed("192.168.178.130")
    assert config.is_allowed("10.0.0.7")
    assert not config.is_allowed("192.168.178.131")
    assert not config.is_allowed("not-an-ip")


@pytest.mark.parametrize("options", [
    {"poll_interval": 5},
    {"poll_interval": 4000},
    {"poll_interval": "60"},
    {"allowed_device_ips": ["192.168.178.300"]},
    {"allowed_device_ips": "192.168.178.130"},
    {"log_level": "verbose"},
    {"log_requests": "yes"},
])
def test_invalid_options_fail_closed(tmp_path, options):
    (tmp_path / "options.json").write_text(json.dumps(options))
    with pytest.raises(ConfigError):
        load_config(env(tmp_path))


def test_port_overrides(tmp_path):
    config = load_config({**env(tmp_path), "SYR_LOCAL_DEVICE_PORT": "9443", "SYR_LOCAL_STATE_PORT": "9099"})
    assert (config.device_port, config.state_port) == (9443, 9099)


def test_identity_roundtrip(tmp_path):
    path = tmp_path / "identity.json"
    assert load_identity(path) == Identity()
    save_identity(path, Identity(serial="204033438", model="LEXplus10S"))
    assert load_identity(path) == Identity(serial="204033438", model="LEXplus10S")
    assert json.loads(path.read_text()) == {"serial": "204033438", "model": "LEXplus10S"}


def test_identity_ignores_garbage(tmp_path):
    path = tmp_path / "identity.json"
    path.write_text("{not json")
    assert load_identity(path) == Identity()
    path.write_text(json.dumps({"serial": "../etc", "model": 5}))
    assert load_identity(path) == Identity()
