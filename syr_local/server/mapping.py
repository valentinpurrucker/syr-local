"""Map raw SYR getter values to the semantic state contract (schema version 1).

Pure functions only. Each semantic value has one row in `VALUE_RULES`;
supporting another model means adding rows, not code paths.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, tzinfo
from typing import Any

SCHEMA_VERSION = 1

_SERIAL = re.compile(r"[A-Za-z0-9-]{1,32}")
_MAC = re.compile(r"[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}")


@dataclass(frozen=True)
class Identity:
    """The part of the device identity that is persisted across restarts."""

    serial: str | None = None
    model: str | None = None


def _parse_number(raw: str) -> float | None:
    try:
        value = float(raw)
    except ValueError:
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return value


def _parse_int(raw: str) -> int | None:
    value = _parse_number(raw)
    return int(value) if value is not None and value.is_integer() else None


# Converters receive the stripped, non-empty raw value and the device's time zone.
Converter = Callable[[str, tzinfo], Any]


def _int(raw: str, tz: tzinfo) -> int | None:
    return _parse_int(raw)


def _float(raw: str, tz: tzinfo) -> float | None:
    return _parse_number(raw)


def _pressure_bar(raw: str, tz: tzinfo) -> float | None:
    # Reported in 1/10 bar; 255 means "invalid / no sensor".
    value = _parse_int(raw)
    if value is None or value == 255:
        return None
    return value / 10


def _flag(raw: str, tz: tzinfo) -> bool | None:
    return {"0": False, "1": True}.get(raw)


def _text(raw: str, tz: tzinfo) -> str | None:
    return raw


def _local_timestamp(raw: str, tz: tzinfo) -> str | None:
    # The device counts seconds of its local wall time, not UTC (documented by
    # alexhass/syr_connect for the same firmware family), so the epoch is read
    # as wall time in `tz` and then converted to UTC. 0 means "never".
    seconds = _parse_int(raw)
    if not seconds:
        return None
    try:
        wall = datetime.fromtimestamp(seconds, UTC).replace(tzinfo=tz)
    except (OverflowError, OSError, ValueError):
        return None
    return wall.astimezone(UTC).isoformat()


@dataclass(frozen=True)
class ValueRule:
    key: str
    getter: str
    convert: Converter
    # Keep the key with a null value when the device reports an empty string
    # (status/alarm: empty means "nothing to report").
    empty_is_null: bool = False


VALUE_RULES: tuple[ValueRule, ...] = (
    ValueRule("salt_weeks", "getSS1", _int),
    ValueRule("salt_kg", "getSV1", _float),
    # L/h: alexhass/syr_connect maps getFLO to l/h; the older syrlex2mqtt notes
    # say L/min. Unconfirmed on this unit.
    ValueRule("flow_lph", "getFLO", _float),
    ValueRule("remaining_capacity_l", "getRES", _int),
    ValueRule("total_water_l", "getCOF", _int),
    ValueRule("regeneration_running", "getRG1", _flag),
    ValueRule("resin_percent", "getCS1", _int),
    ValueRule("pressure_bar", "getPRS", _pressure_bar),
    ValueRule("last_regeneration", "getLAR", _local_timestamp),
    ValueRule("regeneration_count", "getTOR", _int),
    ValueRule("status", "getSTA", _text, empty_is_null=True),
    ValueRule("alarm", "getALM", _text, empty_is_null=True),
)

VALUE_KEYS: tuple[str, ...] = tuple(rule.key for rule in VALUE_RULES)
READING_GETTERS: frozenset[str] = frozenset(rule.getter for rule in VALUE_RULES)


def semantic_values(raw: Mapping[str, str], tz: tzinfo = UTC) -> dict[str, Any]:
    """Return the semantic values; keys without a usable value are omitted."""
    values: dict[str, Any] = {}
    for rule in VALUE_RULES:
        if rule.getter not in raw:
            continue
        text = raw[rule.getter].strip()
        if text:
            value = rule.convert(text, tz)
            if value is not None:
                values[rule.key] = value
        elif rule.empty_is_null:
            values[rule.key] = None
    return values


def device_identity(
    raw: Mapping[str, str], source_ip: str | None, known: Identity
) -> dict[str, str | None]:
    """Return the `device` object of the contract. Every key is always present."""
    firmware = " ".join(part for part in (raw.get("getFIR"), raw.get("getVER")) if part)
    manufacturer = raw.get("getMAN") or "SYR"
    if manufacturer.lower() == "syr":
        manufacturer = "SYR"
    mac = raw.get("getMAC", "")
    return {
        "serial": valid_serial(raw.get("getSRN")) or known.serial,
        "manufacturer": manufacturer,
        "model": raw.get("getCNA") or known.model,
        "firmware": firmware or None,
        "type": raw.get("getTYP") or None,
        "mac": mac.lower() if _MAC.fullmatch(mac) else None,
        "ip": raw.get("getIPA") or source_ip,
    }


def valid_serial(serial: str | None) -> str | None:
    """Return the serial if it is safe to use as an identifier, else None."""
    if serial and _SERIAL.fullmatch(serial):
        return serial
    return None
