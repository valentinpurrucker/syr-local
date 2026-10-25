"""Announce the state API to Home Assistant via Supervisor add-on discovery."""

from __future__ import annotations

import json
import logging
import socket
import threading
import urllib.request
from typing import Any

_LOGGER = logging.getLogger(__name__)

SERVICE = "syr_local"
SUPERVISOR_URL = "http://supervisor"
RETRY_DELAYS_S = (5, 10, 20, 40, 60, 120)
HTTP_TIMEOUT_S = 10


class DiscoveryAnnouncer:
    """Send `{"host", "port", "serial"}` for the `syr_local` service.

    Runs in a background thread with retries, because Home Assistant may still
    be starting. Without SUPERVISOR_TOKEN (standalone/dev) it does nothing.
    """

    def __init__(
        self,
        token: str | None,
        port: int,
        base_url: str = SUPERVISOR_URL,
        retry_delays_s: tuple[float, ...] = RETRY_DELAYS_S,
    ) -> None:
        self._token = token
        self._port = port
        self._base_url = base_url
        self._retry_delays_s = retry_delays_s
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._serial: str | None = None
        self._thread: threading.Thread | None = None

    @property
    def enabled(self) -> bool:
        return bool(self._token)

    def announce(self, serial: str) -> None:
        """Announce `serial` unless it is already announced or being announced."""
        if not self.enabled:
            _LOGGER.debug("No SUPERVISOR_TOKEN; skipping discovery")
            return
        with self._lock:
            if serial == self._serial:
                return
            self._serial = serial
            self._thread = threading.Thread(
                target=self._run, args=(serial,), name="discovery", daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def _run(self, serial: str) -> None:
        for delay in (0, *self._retry_delays_s):
            if self._stop.wait(delay) or serial != self._serial:
                return
            try:
                config = {"host": self._hostname(), "port": self._port, "serial": serial}
                result = self._request("POST", "/discovery", {"service": SERVICE, "config": config})
            except (OSError, ValueError) as err:
                _LOGGER.info("Discovery not sent yet (%s); retrying", err)
                continue
            _LOGGER.info(
                "Discovery sent for %s at %s:%s (%s)",
                serial, config["host"], self._port, result.get("data", {}).get("uuid"),
            )
            return
        _LOGGER.warning("Giving up on discovery; set up the integration manually")

    def _hostname(self) -> str:
        try:
            info = self._request("GET", "/addons/self/info")
            hostname = info["data"]["hostname"]
            if isinstance(hostname, str) and hostname:
                return hostname
        except (OSError, ValueError, KeyError, TypeError) as err:
            _LOGGER.debug("Cannot read add-on hostname from Supervisor: %s", err)
        return socket.gethostname()

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            self._base_url + path,
            data=data,
            method=method,
            headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:
            result = json.loads(response.read() or b"{}")
        if not isinstance(result, dict) or result.get("result", "ok") != "ok":
            raise ValueError(f"unexpected Supervisor response: {result!r}")
        return result
