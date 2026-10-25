"""TLS server that stands in for syrconnect.de towards the device.

Only POST to the two ASMX endpoints is served. Every other method and path,
including the firmware check `GET /firmware/saocal2/scf.cfg`, gets a 404, and
so does any request for a `maintenance.*` host. Nothing is ever forwarded to
the real cloud.
"""

from __future__ import annotations

import json
import logging
import ssl
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .catalog import UnsafeCommandError
from .config import Config
from .mapping import Identity
from .planner import CommandPlanner, Endpoint
from .protocol import (
    MAX_BODY_BYTES,
    MessageTooLargeError,
    build_response,
    decode_text,
    parse_request_body,
)
from .state import DeviceState

_LOGGER = logging.getLogger(__name__)

ASMX_PREFIX = "/WebServices/SyrConnectLimexWebService.asmx/"
ROUTES: dict[str, Endpoint] = {ASMX_PREFIX + endpoint.value: endpoint for endpoint in Endpoint}
REQUEST_TIMEOUT_S = 15
MAX_CONNECTIONS = 32


@dataclass
class DeviceContext:
    config: Config
    state: DeviceState
    planner: CommandPlanner
    on_identity: Callable[[Identity], None]
    request_log: logging.Logger | None = None
    clock: Callable[[], float] = time.monotonic


class DeviceRequestHandler(BaseHTTPRequestHandler):
    server: DeviceServer
    protocol_version = "HTTP/1.1"
    server_version = "syr-local"
    sys_version = ""
    timeout = REQUEST_TIMEOUT_S

    def do_POST(self) -> None:
        context = self.server.context
        client_ip = self.client_address[0]
        if not context.config.is_allowed(client_ip):
            _LOGGER.warning("Rejected request from %s (not in allowed_device_ips)", client_ip)
            self._send_status(403)
            return
        host = self.headers.get("Host", "").strip().lower()
        if host.startswith("maintenance."):
            self._send_status(404)
            return
        endpoint = ROUTES.get(self.path.split("?", 1)[0])
        if endpoint is None:
            self._send_status(404)
            return

        body = self._read_body()
        if body is None:
            return
        self._log_raw(client_ip, host, body)
        try:
            values = parse_request_body(body)
        except MessageTooLargeError as err:
            _LOGGER.warning("Rejected request from %s: %s", client_ip, err)
            self._send_status(413)
            return

        identity = context.state.record(values, client_ip, datetime.now(UTC))
        if identity is not None:
            context.on_identity(identity)
        if values:
            _LOGGER.debug("Raw values from %s: %s", client_ip, values)

        try:
            reply = build_response(context.planner.commands_for(endpoint, context.clock()))
        except UnsafeCommandError:
            # Fail closed: send nothing rather than a command we did not vet.
            _LOGGER.exception("Refused to build response")
            self._send_status(500)
            return
        self._send(200, reply.encode("utf-8"), "text/xml; charset=utf-8")

    def do_GET(self) -> None:
        # Includes the firmware check (GET /firmware/saocal2/scf.cfg). It must
        # never be answered, or the device could start a firmware update.
        _LOGGER.info(
            "Refused GET %s for host %s from %s (404)",
            self.path[:200], self.headers.get("Host", "")[:100], self.client_address[0],
        )
        self._send_status(404)

    def _not_found(self) -> None:
        self._send_status(404)

    do_HEAD = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _not_found
    do_TRACE = do_CONNECT = _not_found

    def _read_body(self) -> bytes | None:
        if self.headers.get("Transfer-Encoding"):
            self._send_status(411)
            return None
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._send_status(400)
            return None
        if length < 0:
            self._send_status(400)
            return None
        if length > MAX_BODY_BYTES:
            self._send_status(413)
            return None
        return self.rfile.read(length)

    def _send_status(self, status: int) -> None:
        self._send(status, b"", None)

    def _send(self, status: int, body: bytes, content_type: str | None) -> None:
        self.close_connection = True
        self.send_response(status)
        if content_type:
            self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _log_raw(self, client_ip: str, host: str, body: bytes) -> None:
        request_log = self.server.context.request_log
        if request_log is None:
            return
        record: dict[str, Any] = {
            "t": datetime.now(UTC).isoformat(timespec="seconds"),
            "ip": client_ip,
            "host": host,
            "path": self.path,
            "body": decode_text(body),
        }
        request_log.info(json.dumps(record, ensure_ascii=False))

    def log_message(self, format: str, *args: Any) -> None:
        _LOGGER.debug("%s %s", self.client_address[0], format % args)


class DeviceServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self, address: tuple[str, int], context: DeviceContext, tls: ssl.SSLContext
    ) -> None:
        super().__init__(address, DeviceRequestHandler)
        self.context = context
        self._slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        # The TLS handshake runs lazily in the handler thread (bounded by the
        # handler timeout), so a stalled client cannot block accept().
        self.socket = tls.wrap_socket(
            self.socket, server_side=True, do_handshake_on_connect=False
        )

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()

    def handle_error(self, request: Any, client_address: Any) -> None:
        # TLS handshake failures and client resets are expected noise.
        _LOGGER.debug("Connection error from %s", client_address[0], exc_info=True)
