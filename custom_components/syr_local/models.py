"""Parse and validate the SYR Local add-on state document (schema version 1).

Pure standard library, no Home Assistant imports, so it can be unit-tested
on its own. The value keys must match the add-on's `server/mapping.py`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any

SCHEMA_VERSION = 1

# Semantic value key -> expected JSON type. Unknown keys are ignored, so the
# add-on can add values without breaking older integrations.
VALUE_TYPES: Mapping[str, str] = MappingProxyType(
    {
        "salt_weeks": "number",
        "salt_kg": "number",
        "flow_lph": "number",
        "remaining_capacity_l": "number",
        "total_water_l": "number",
        "regeneration_running": "bool",
        "resin_percent": "number",
        "pressure_bar": "number",
        "last_regeneration": "timestamp",
        "regeneration_count": "number",
        "status": "text",
        "alarm": "text",
    }
)


class SyrLocalError(Exception):
    """Base error of the SYR Local integration."""


class InvalidStateError(SyrLocalError):
    """The add-on returned a payload that does not match the contract."""


class UnsupportedVersionError(InvalidStateError):
    """The add-on speaks a schema version this integration does not support."""


@dataclass(frozen=True)
class DeviceInfo:
    serial: str | None
    manufacturer: str | None
    model: str | None
    firmware: str | None
    mac: str | None
    ip: str | None


@dataclass(frozen=True)
class SyrLocalState:
    device: DeviceInfo
    values: Mapping[str, Any] = field(default_factory=dict)
    last_seen: datetime | None = None
    last_read: datetime | None = None
    request_count: int = 0


def parse_state(payload: Any) -> SyrLocalState:
    """Validate a decoded JSON payload and return the parsed state."""
    if not isinstance(payload, dict):
        raise InvalidStateError("state payload is not a JSON object")
    version = payload.get("schema_version")
    if version != SCHEMA_VERSION or isinstance(version, bool):
        raise UnsupportedVersionError(f"unsupported schema_version {version!r}")
    device = _object(payload, "device")
    raw_values = _object(payload, "values")
    meta = _object(payload, "meta")

    request_count = meta.get("request_count", 0)
    if isinstance(request_count, bool) or not isinstance(request_count, int):
        raise InvalidStateError("meta.request_count is not an integer")

    return SyrLocalState(
        device=DeviceInfo(
            serial=_optional_text(device, "serial"),
            manufacturer=_optional_text(device, "manufacturer"),
            model=_optional_text(device, "model"),
            firmware=_optional_text(device, "firmware"),
            mac=_optional_text(device, "mac"),
            ip=_optional_text(device, "ip"),
        ),
        values=MappingProxyType(_values(raw_values)),
        last_seen=_optional_time(meta, "last_seen"),
        last_read=_optional_time(meta, "last_read"),
        request_count=request_count,
    )


def _object(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise InvalidStateError(f"{key} is not a JSON object")
    return value


def _optional_text(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidStateError(f"{key} is not a string")
    return value or None


def _optional_time(data: dict[str, Any], key: str) -> datetime | None:
    text = _optional_text(data, key)
    if text is None:
        return None
    moment = _parse_time(text)
    if moment is None:
        raise InvalidStateError(f"{key} is not an ISO-8601 timestamp with time zone")
    return moment


def _parse_time(text: str) -> datetime | None:
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None


def _values(raw: dict[str, Any]) -> dict[str, Any]:
    """Keep known keys with a value of the expected type; drop anything else."""
    values: dict[str, Any] = {}
    for key, kind in VALUE_TYPES.items():
        if key not in raw:
            continue
        value = raw[key]
        if kind == "number" and isinstance(value, int | float) and not isinstance(value, bool):
            values[key] = value
        elif kind == "bool" and isinstance(value, bool):
            values[key] = value
        elif kind == "timestamp" and isinstance(value, str) and (moment := _parse_time(value)):
            values[key] = moment
        elif kind == "text" and (value is None or isinstance(value, str)):
            values[key] = value
    return values
