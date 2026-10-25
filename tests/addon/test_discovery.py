import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from server.discovery import DiscoveryAnnouncer


class FakeSupervisor(ThreadingHTTPServer):
    def __init__(self, fail_posts: int = 0, info_status: int = 200):
        super().__init__(("127.0.0.1", 0), FakeSupervisorHandler)
        self.fail_posts = fail_posts
        self.info_status = info_status
        self.requests: list[tuple[str, str, str | None, dict | None]] = []
        self.done = threading.Event()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"


class FakeSupervisorHandler(BaseHTTPRequestHandler):
    server: FakeSupervisor

    def _record(self, body):
        self.server.requests.append(
            (self.command, self.path, self.headers.get("Authorization"), body)
        )

    def do_GET(self):
        self._record(None)
        if self.path == "/addons/self/info" and self.server.info_status == 200:
            self._json(200, {"result": "ok", "data": {"hostname": "local-syr-local"}})
        else:
            self._json(self.server.info_status, {"result": "error"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self._record(body)
        if self.server.fail_posts > 0:
            self.server.fail_posts -= 1
            self._json(503, {"result": "error", "message": "starting"})
            return
        self._json(200, {"result": "ok", "data": {"uuid": "abc"}})
        self.server.done.set()

    def _json(self, status, payload):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@pytest.fixture
def supervisor(request):
    server = FakeSupervisor(**getattr(request, "param", {}))
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    yield server
    server.shutdown()
    server.server_close()


def posts(server):
    return [r for r in server.requests if r[0] == "POST"]


def test_announces_hostname_port_serial(supervisor):
    announcer = DiscoveryAnnouncer("token", 8099, base_url=supervisor.url, retry_delays_s=(0.05,))
    announcer.announce("204033438")
    assert supervisor.done.wait(5)
    announcer.join(5)
    assert posts(supervisor) == [(
        "POST", "/discovery", "Bearer token",
        {"service": "syr_local", "config": {"host": "local-syr-local", "port": 8099, "serial": "204033438"}},
    )]


@pytest.mark.parametrize("supervisor", [{"fail_posts": 2}], indirect=True)
def test_retries_until_supervisor_accepts(supervisor):
    announcer = DiscoveryAnnouncer("token", 8099, base_url=supervisor.url, retry_delays_s=(0.05,) * 5)
    announcer.announce("204033438")
    assert supervisor.done.wait(5)
    announcer.join(5)
    assert len(posts(supervisor)) == 3


@pytest.mark.parametrize("supervisor", [{"info_status": 403}], indirect=True)
def test_falls_back_to_socket_hostname(supervisor, monkeypatch):
    monkeypatch.setattr("server.discovery.socket.gethostname", lambda: "container-host")
    announcer = DiscoveryAnnouncer("token", 8099, base_url=supervisor.url, retry_delays_s=())
    announcer.announce("204033438")
    assert supervisor.done.wait(5)
    announcer.join(5)
    assert posts(supervisor)[0][3]["config"]["host"] == "container-host"


def test_same_serial_is_announced_once(supervisor):
    announcer = DiscoveryAnnouncer("token", 8099, base_url=supervisor.url, retry_delays_s=())
    announcer.announce("204033438")
    assert supervisor.done.wait(5)
    announcer.join(5)
    announcer.announce("204033438")
    announcer.join(5)
    assert len(posts(supervisor)) == 1


def test_without_token_nothing_is_sent(supervisor):
    announcer = DiscoveryAnnouncer(None, 8099, base_url=supervisor.url)
    announcer.announce("204033438")
    announcer.join(1)
    assert supervisor.requests == []
