"""Read-only getter catalog for the SYR Connect polling protocol.

In this protocol the server tells the device what to do: every command in a
response is executed by the device. A `set...` command changes the device, so
this module is the single place that decides which command names may ever be
sent. Only `getXXX` names are allowed, and `getSIR` is refused as well because
SIR is the regeneration trigger.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

READ_ONLY_PATTERN = re.compile(r"get[A-Z0-9]{2,4}")

# Refused even though they look like getters.
FORBIDDEN: frozenset[str] = frozenset({"getSIR"})

# What the SYR cloud asks in reply to GetBasicCommands (identity only).
BASIC_GETTERS: tuple[str, ...] = ("getSRN", "getVER", "getFIR", "getTYP", "getCNA")

# Full read-only catalog for a LEXplus10S, based on the getter list the SYR
# cloud uses (syrlex2mqtt doc/syrconnect-protocol.md) plus the consumption
# statistics, without getSIR. Another model would get its own tuple here.
FULL_GETTERS: tuple[str, ...] = (
    *BASIC_GETTERS,
    "getALM", "getCDE", "getCS1", "getCS2", "getCS3", "getCYN", "getCYT",
    "getDEN", "getDGW", "getDWF", "getFCO", "getFLO", "getINR", "getIPA",
    "getIWH", "getLAR", "getMAC", "getMAN", "getNOR", "getNOT", "getOWH",
    "getPRS", "getPST", "getRDO", "getRES", "getRG1", "getRG2", "getRG3",
    "getRPD", "getRPW", "getRTH", "getRTI", "getRTM", "getSCR", "getSRE",
    "getSS1", "getSS2", "getSS3", "getSTA", "getSV1", "getSV2", "getSV3",
    "getTOR", "getVS1", "getVS2", "getVS3", "getWHU",
    "getTOF", "getYEF", "getCWF", "getLWF", "getCMF", "getLMF", "getCOF",
)

# Only names from this set are kept from incoming device requests. The device
# answers the getters we asked for, so anything else is noise or an attempt to
# grow the in-memory map without bound.
KNOWN_GETTERS: frozenset[str] = frozenset((*BASIC_GETTERS, *FULL_GETTERS))


class UnsafeCommandError(ValueError):
    """Raised when something other than a plain read-only getter would be sent."""


def is_getter_name(name: str) -> bool:
    """Return True if `name` has the shape of a getter (used for incoming values too)."""
    return READ_ONLY_PATTERN.fullmatch(name) is not None


def ensure_read_only(names: Iterable[str]) -> tuple[str, ...]:
    """Return `names` as a tuple, or raise if any name is not a permitted getter."""
    checked = tuple(names)
    for name in checked:
        if not isinstance(name, str) or not is_getter_name(name):
            raise UnsafeCommandError(f"refusing to send non-getter command {name!r}")
        if name in FORBIDDEN:
            raise UnsafeCommandError(f"refusing to send forbidden command {name!r}")
    return checked
