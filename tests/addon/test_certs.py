import os
import stat
import subprocess
from datetime import UTC, datetime, timedelta

from server.certs import ensure_certificates


def openssl_text(path) -> str:
    return subprocess.run(
        ["openssl", "x509", "-in", str(path), "-noout", "-text"],
        check=True, capture_output=True, text=True,
    ).stdout


def test_leaf_certificate(certs):
    text = openssl_text(certs.leaf_cert)
    assert "DNS:syrconnect.de" in text
    assert "DNS:*.syrconnect.de" in text
    assert "IP Address:212.77.236.30" in text
    assert "Public-Key: (2048 bit)" in text
    assert "sha256WithRSAEncryption" in text
    assert "CA:FALSE" in text
    assert "TLS Web Server Authentication" in text


def test_ca_certificate(certs):
    text = openssl_text(certs.ca_cert)
    assert "CA:TRUE" in text
    assert "Public-Key: (2048 bit)" in text


def test_validity_ten_years(certs):
    end = subprocess.run(
        ["openssl", "x509", "-in", str(certs.leaf_cert), "-noout", "-enddate"],
        check=True, capture_output=True, text=True,
    ).stdout.strip().split("=", 1)[1]
    not_after = datetime.strptime(end, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=UTC)
    assert not_after - datetime.now(UTC) > timedelta(days=3640)


def test_chain_is_leaf_plus_ca_and_verifies(certs):
    assert certs.chain.read_bytes() == certs.leaf_cert.read_bytes() + certs.ca_cert.read_bytes()
    result = subprocess.run(
        ["openssl", "verify", "-CAfile", str(certs.ca_cert), str(certs.leaf_cert)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_keys_are_private_and_persisted(certs):
    for key in (certs.leaf_key, certs.leaf_key.parent / "ca.key"):
        assert stat.S_IMODE(os.stat(key).st_mode) == 0o600
    before = certs.chain.read_bytes()
    again = ensure_certificates(certs.chain.parent)
    assert again == certs
    assert certs.chain.read_bytes() == before
    assert sorted(p.name for p in certs.chain.parent.iterdir()) == [
        "ca.crt", "ca.key", "chain.crt", "server.crt", "server.key",
    ]
