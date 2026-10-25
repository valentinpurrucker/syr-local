"""Diagnostics for SYR Local."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .coordinator import SyrLocalConfigEntry

TO_REDACT = {"serial", "mac", "ip", "unique_id", "title"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SyrLocalConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    state = coordinator.data
    return {
        "entry": async_redact_data(
            {"title": entry.title, "unique_id": entry.unique_id, "data": dict(entry.data)},
            TO_REDACT,
        ),
        "addon_url": str(coordinator.client.url),
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval_s": coordinator.update_interval.total_seconds()
            if coordinator.update_interval
            else None,
            "last_exception": repr(coordinator.last_exception)
            if coordinator.last_exception
            else None,
            "device_online": coordinator.device_online,
        },
        "state": async_redact_data(
            {
                "device": asdict(state.device),
                "values": dict(state.values),
                "last_seen": state.last_seen,
                "last_read": state.last_read,
                "request_count": state.request_count,
            },
            TO_REDACT,
        )
        if state
        else None,
    }
