"""Internal HTTP API for the Home Assistant integration (not published to the host)."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, tzinfo
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .state import DeviceState, state_document

_LOGGER = logging.getLogger(__name__)

STATE_PATH = "/api/v1/state"
HEALTH_PATH = "/health"


class StateRequestHandler(BaseHTTPRequestHandler):
    server: StateServer
    server_version = "syr-local"
    sys_version = ""
    timeout = 10

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == STATE_PATH:
            server = self.server
            document = state_document(server.state.snapshot(), server.now(), server.tz)
            self._send_json(200, document)
        elif path == HEALTH_PATH:
            self._send_json(200, {"status": "ok"})
        else:
            self._send_json(404, {"error": "not_found"})

    def _not_found(self) -> None:
        self._send_json(404, {"error": "not_found"})

    do_HEAD = do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _not_found

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        _LOGGER.debug("%s %s", self.client_address[0], format % args)


class StateServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        state: DeviceState,
        tz: tzinfo,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        super().__init__(address, StateRequestHandler)
        self.state = state
        self.tz = tz
        self.now = now
