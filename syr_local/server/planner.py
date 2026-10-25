"""Decide which getters to request in reply to a device poll."""

from __future__ import annotations

import threading
from enum import StrEnum

from .catalog import BASIC_GETTERS, FULL_GETTERS


class Endpoint(StrEnum):
    BASIC = "GetBasicCommands"
    ALL = "GetAllCommands"


class CommandPlanner:
    """Request the full catalog at most once per interval; otherwise nothing.

    The device polls every ~11 s and answers the getters in its next request.
    An empty reply means "nothing to do", so the device stays idle between reads.
    """

    def __init__(self, interval_s: float) -> None:
        self._interval_s = interval_s
        self._last_full: float | None = None
        self._lock = threading.Lock()

    def commands_for(self, endpoint: Endpoint, now: float) -> tuple[str, ...]:
        """Return the getters for this poll. `now` is a monotonic clock in seconds."""
        if endpoint is Endpoint.BASIC:
            return BASIC_GETTERS
        with self._lock:
            if self._last_full is None or now - self._last_full >= self._interval_s:
                self._last_full = now
                return FULL_GETTERS
        return ()
