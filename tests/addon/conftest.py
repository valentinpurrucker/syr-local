from __future__ import annotations

import http.client
import shutil
import ssl
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest

from server.certs import CertPaths, ensure_certificates, server_tls_context
from server.config import Config
from server.device_server import DeviceContext, DeviceServer
from server.mapping import Identity
from server.planner import CommandPlanner
from server.state import DeviceState
from server.state_api import StateServer


@pytest.fixture(scope="session")
def certs(tmp_path_factory: pytest.TempPathFactory) -> CertPaths:
    if shutil.which("openssl") is None:
        pytest.skip("openssl CLI not available")
    return ensure_certificates(tmp_path_factory.mktemp("certs"))


@dataclass
class Clock:
    now: float = 1000.0

    def __call__(self) -> float:
        return self.now


@dataclass
class Running:
    device_port: int
    state_port: int
    state: DeviceState
    clock: Clock
    identities: list[Identity] = field(default_factory=list)

    def device(self, method: str, path: str, body: bytes = b"", host: str = "syrconnect.de",
               headers: dict[str, str] | None = None) -> tuple[int, bytes]:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        conn = http.client.HTTPSConnection("127.0.0.1", self.device_port, context=context, timeout=5)
        try:
            conn.request(method, path, body=body, headers={"Host": host, **(headers or {})})
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def api(self, method: str, path: str) -> tuple[int, bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", self.state_port, timeout=5)
        try:
            conn.request(method, path)
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()


def start_servers(certs: CertPaths, config: Config) -> tuple[Running, list]:
    state = DeviceState(datetime(2026, 10, 25, 14, 0, tzinfo=UTC), Identity())
    clock = Clock()
    identities: list[Identity] = []
    context = DeviceContext(
        config=config,
        state=state,
        planner=CommandPlanner(config.poll_interval),
        on_identity=identities.append,
        clock=clock,
    )
    device = DeviceServer(("127.0.0.1", 0), context, server_tls_context(certs))
    api = StateServer(("127.0.0.1", 0), state, UTC)
    servers = [device, api]
    for server in servers:
        threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    running = Running(device.server_address[1], api.server_address[1], state, clock, identities)
    return running, servers


@pytest.fixture
def running(certs: CertPaths, tmp_path: Path) -> Iterator[Running]:
    running, servers = start_servers(certs, Config(data_dir=tmp_path, poll_interval=60))
    yield running
    for server in servers:
        server.shutdown()
        server.server_close()
