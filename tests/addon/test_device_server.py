import ipaddress
import json
import re
import shutil
import socket
import ssl
import subprocess

import pytest

from server.catalog import BASIC_GETTERS, FULL_GETTERS
from server.config import Config, load_config
from server.protocol import MAX_BODY_BYTES

from .conftest import start_servers
from .fixtures import FULL_VALUES, form_body

BASIC = "/WebServices/SyrConnectLimexWebService.asmx/GetBasicCommands"
ALL = "/WebServices/SyrConnectLimexWebService.asmx/GetAllCommands"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}


def names(reply: bytes) -> list[str]:
    text = reply.decode()
    assert 'n="set' not in text.lower() and "getSIR" not in text
    commands = re.findall(r'<c n="([^"]+)" v="([^"]*)" />', text)
    assert all(value == "" for _, value in commands)
    return [name for name, _ in commands]


def test_basic_commands(running):
    status, reply = running.device("POST", BASIC)
    assert status == 200
    assert names(reply) == list(BASIC_GETTERS)


def test_full_then_empty_then_full(running):
    status, reply = running.device("POST", ALL, form_body({"getSRN": "204033438"}), headers=FORM)
    assert status == 200 and names(reply) == list(FULL_GETTERS)

    running.clock.now += 11
    status, reply = running.device("POST", ALL, b"", headers=FORM)
    assert status == 200
    assert reply == b'<?xml version="1.0" encoding="utf-8"?><sc version="1.0"><d></d></sc>'

    running.clock.now += 60
    status, reply = running.device("POST", ALL)
    assert names(reply) == list(FULL_GETTERS)


def test_values_reach_state_api_and_identity_callback(running):
    running.device("POST", ALL, form_body(FULL_VALUES), headers=FORM)
    status, body = running.api("GET", "/api/v1/state")
    assert status == 200
    document = json.loads(body)
    assert document["device"]["serial"] == "204033438"
    assert document["device"]["ip"] == "192.168.178.130"
    assert document["values"]["salt_weeks"] == 5
    assert document["meta"]["request_count"] == 1
    assert [identity.serial for identity in running.identities] == ["204033438"]


@pytest.mark.parametrize(
    "path",
    ["/firmware/saocal2/scf.cfg", "/", BASIC, ALL, "/WebServices/SyrConnectLimexWebService.asmx"],
)
def test_every_get_is_404(running, path):
    status, body = running.device("GET", path, host="firmware.syrconnect.de")
    assert status == 404
    assert body == b""


@pytest.mark.parametrize(
    "method", ["PUT", "DELETE", "PATCH", "OPTIONS", "HEAD", "TRACE", "CONNECT"]
)
def test_other_methods_are_404(running, method):
    assert running.device(method, BASIC)[0] == 404


def test_maintenance_host_is_404(running):
    status, _ = running.device("POST", "/GetBasicCommands", host="maintenance.syrconnect.de")
    assert status == 404
    status, _ = running.device("POST", BASIC, host="Maintenance.syrconnect.de:443")
    assert status == 404
    assert running.state.snapshot().request_count == 0


@pytest.mark.parametrize("path", ["/GetBasicCommands", "/GetAllCommands", BASIC + "x", "/WebServices/x"])
def test_unknown_post_paths_are_404(running, path):
    assert running.device("POST", path)[0] == 404


def test_query_string_is_ignored(running):
    assert running.device("POST", BASIC + "?x=1")[0] == 200


def test_body_cap(running):
    # The server rejects on the declared length without reading the body.
    status, _ = running.device("POST", ALL, headers={"Content-Length": str(MAX_BODY_BYTES + 1)})
    assert status == 413
    assert running.state.snapshot().request_count == 0


def test_chunked_body_is_refused(running):
    status, _ = running.device("POST", ALL, headers={"Transfer-Encoding": "chunked"})
    assert status == 411


def test_allowlist_blocks_other_sources(certs, tmp_path):
    (tmp_path / "options.json").write_text(json.dumps({"allowed_device_ips": ["192.168.178.130"]}))
    config = load_config({"SYR_LOCAL_DATA_DIR": str(tmp_path)})
    running, servers = start_servers(certs, config)
    try:
        assert running.device("POST", BASIC)[0] == 403
        assert running.state.snapshot().request_count == 0
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()


def test_allowlist_permits_listed_network(certs, tmp_path):
    config = Config(data_dir=tmp_path, allowed_device_ips=(ipaddress.ip_network("127.0.0.0/8"),))
    running, servers = start_servers(certs, config)
    try:
        assert running.device("POST", BASIC)[0] == 200
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()


def test_legacy_rsa_cipher_tls12(running):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    context.maximum_version = ssl.TLSVersion.TLSv1_2
    context.set_ciphers("AES256-SHA")
    with socket.create_connection(("127.0.0.1", running.device_port), timeout=5) as raw:
        with context.wrap_socket(raw) as tls:
            assert tls.version() == "TLSv1.2"
            assert tls.cipher()[0] == "AES256-SHA"


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_tls11_is_refused(running):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        context.minimum_version = ssl.TLSVersion.TLSv1_1
        context.maximum_version = ssl.TLSVersion.TLSv1_1
        context.set_ciphers("DEFAULT:@SECLEVEL=0")
    except (ValueError, ssl.SSLError):
        pytest.skip("TLS 1.1 not available in this OpenSSL build")
    with socket.create_connection(("127.0.0.1", running.device_port), timeout=5) as raw:
        with pytest.raises(ssl.SSLError):
            context.wrap_socket(raw)


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl CLI not available")
def test_openssl_s_client_aes256_sha(running):
    result = subprocess.run(
        ["openssl", "s_client", "-connect", f"127.0.0.1:{running.device_port}",
         "-tls1_2", "-cipher", "AES256-SHA", "-servername", "syrconnect.de"],
        input=b"", capture_output=True, timeout=20,
    )
    output = result.stdout.decode(errors="replace")
    assert "Cipher is AES256-SHA" in output or "Cipher    : AES256-SHA" in output, output
    assert "TLSv1.2" in output
