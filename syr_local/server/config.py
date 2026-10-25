"""Add-on configuration from /data/options.json (written by the Supervisor)."""

from __future__ import annotations

import ipaddress
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

LOG_LEVELS = ("debug", "info", "warning", "error")


class ConfigError(ValueError):
    """Raised for invalid add-on options."""


@dataclass(frozen=True)
class Config:
    data_dir: Path = Path("/data")
    poll_interval: int = 60
    allowed_device_ips: tuple[IPNetwork, ...] = ()
    log_level: str = "info"
    log_requests: bool = False
    bind_host: str = "0.0.0.0"
    device_port: int = 8443
    state_port: int = 8099

    @property
    def cert_dir(self) -> Path:
        return self.data_dir / "certs"

    def is_allowed(self, ip: str) -> bool:
        """An empty allowlist allows any source address."""
        if not self.allowed_device_ips:
            return True
        try:
            address = ipaddress.ip_address(ip)
        except ValueError:
            return False
        return any(address in network for network in self.allowed_device_ips)


def load_config(env: dict[str, str] | None = None) -> Config:
    """Read options.json from the data dir; missing file or keys use defaults.

    SYR_LOCAL_DATA_DIR, SYR_LOCAL_DEVICE_PORT and SYR_LOCAL_STATE_PORT override
    the container defaults for running outside the Supervisor.
    """
    env = dict(os.environ) if env is None else env
    data_dir = Path(env.get("SYR_LOCAL_DATA_DIR", "/data"))
    options_file = data_dir / "options.json"
    try:
        options = json.loads(options_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        options = {}
    except (OSError, ValueError) as err:
        raise ConfigError(f"cannot read {options_file}: {err}") from err
    if not isinstance(options, dict):
        raise ConfigError(f"{options_file} must contain a JSON object")

    return Config(
        data_dir=data_dir,
        poll_interval=_int_option(options, "poll_interval", 60, 10, 3600),
        allowed_device_ips=_networks(options.get("allowed_device_ips", [])),
        log_level=_choice(options, "log_level", "info", LOG_LEVELS),
        log_requests=_bool_option(options, "log_requests", False),
        device_port=_port(env, "SYR_LOCAL_DEVICE_PORT", 8443),
        state_port=_port(env, "SYR_LOCAL_STATE_PORT", 8099),
    )


def _int_option(options: dict[str, Any], key: str, default: int, low: int, high: int) -> int:
    value = options.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ConfigError(f"{key} must be an integer between {low} and {high}, got {value!r}")
    return value


def _bool_option(options: dict[str, Any], key: str, default: bool) -> bool:
    value = options.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"{key} must be true or false, got {value!r}")
    return value


def _choice(options: dict[str, Any], key: str, default: str, choices: tuple[str, ...]) -> str:
    value = options.get(key, default)
    if value not in choices:
        raise ConfigError(f"{key} must be one of {', '.join(choices)}, got {value!r}")
    return value


def _networks(values: Any) -> tuple[IPNetwork, ...]:
    # Fail closed: a typo must not silently turn the allowlist into "allow any".
    if not isinstance(values, list):
        raise ConfigError("allowed_device_ips must be a list")
    networks = []
    for value in values:
        try:
            networks.append(ipaddress.ip_network(str(value).strip(), strict=False))
        except ValueError as err:
            raise ConfigError(f"invalid entry in allowed_device_ips: {value!r}") from err
    return tuple(networks)


def _port(env: dict[str, str], key: str, default: int) -> int:
    try:
        port = int(env.get(key, default))
    except ValueError as err:
        raise ConfigError(f"{key} must be a port number") from err
    if not 0 <= port <= 65535:
        raise ConfigError(f"{key} must be a port number")
    return port
