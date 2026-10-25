"""In-memory device state and the versioned state document."""

from __future__ import annotations

import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, tzinfo
from typing import Any

from .mapping import (
    READING_GETTERS,
    SCHEMA_VERSION,
    Identity,
    device_identity,
    semantic_values,
    valid_serial,
)


@dataclass(frozen=True)
class Snapshot:
    """A consistent copy of the device state at one point in time."""

    started_at: datetime
    known_identity: Identity
    raw: Mapping[str, str] = field(default_factory=dict)
    source_ip: str | None = None
    last_seen: datetime | None = None
    last_read: datetime | None = None
    request_count: int = 0


class DeviceState:
    """Thread-safe store for the latest raw getter values of one device.

    Readings live only in memory. Only the identity (serial/model) is seeded
    from disk, so discovery can be sent before the device has been seen again.
    """

    def __init__(self, started_at: datetime, known_identity: Identity) -> None:
        self._lock = threading.Lock()
        self._snapshot = Snapshot(started_at=started_at, known_identity=known_identity)

    def record(
        self, values: Mapping[str, str], source_ip: str, now: datetime
    ) -> Identity | None:
        """Merge one device request. Return the identity if it changed, else None."""
        with self._lock:
            current = self._snapshot
            raw = {**current.raw, **values}
            known = current.known_identity
            changed: Identity | None = None
            serial = valid_serial(raw.get("getSRN"))
            if serial:
                candidate = Identity(serial=serial, model=raw.get("getCNA") or known.model)
                if candidate != known:
                    known = changed = candidate
            reading = any(
                name in READING_GETTERS and value.strip() for name, value in values.items()
            )
            self._snapshot = Snapshot(
                started_at=current.started_at,
                known_identity=known,
                raw=raw,
                source_ip=source_ip,
                last_seen=now,
                last_read=now if reading else current.last_read,
                request_count=current.request_count + 1,
            )
            return changed

    def identity(self) -> Identity:
        with self._lock:
            return self._snapshot.known_identity

    def snapshot(self) -> Snapshot:
        with self._lock:
            return self._snapshot


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat(timespec="seconds") if moment else None


def state_document(snapshot: Snapshot, now: datetime, tz: tzinfo) -> dict[str, Any]:
    """Render the `GET /api/v1/state` JSON document (schema version 1)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _iso(now),
        "device": device_identity(snapshot.raw, snapshot.source_ip, snapshot.known_identity),
        "values": semantic_values(snapshot.raw, tz),
        "meta": {
            "started_at": _iso(snapshot.started_at),
            "last_seen": _iso(snapshot.last_seen),
            "last_read": _iso(snapshot.last_read),
            "request_count": snapshot.request_count,
        },
    }
