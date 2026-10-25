"""Local CA and leaf certificate for the syrconnect.de stand-in.

The device does not pin the SYR certificate (it accepted a mitmproxy CA), so a
self-made CA works. The files are generated once with the openssl CLI and
persisted under /data/certs. The device was captured using TLS 1.2 with RSA key
exchange, so the server keeps those legacy cipher suites enabled.
"""

from __future__ import annotations

import logging
import os
import shutil
import ssl
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

LEAF_SANS = "DNS:syrconnect.de,DNS:*.syrconnect.de,IP:212.77.236.30"
VALIDITY_DAYS = 3650
# Python's default cipher list drops RSA key exchange and SHA-1 MAC suites
# such as AES256-SHA, which the device was captured using.
CIPHERS = "DEFAULT:@SECLEVEL=1"


@dataclass(frozen=True)
class CertPaths:
    ca_cert: Path
    leaf_cert: Path
    leaf_key: Path
    chain: Path  # leaf + CA


def cert_paths(cert_dir: Path) -> CertPaths:
    return CertPaths(
        ca_cert=cert_dir / "ca.crt",
        leaf_cert=cert_dir / "server.crt",
        leaf_key=cert_dir / "server.key",
        chain=cert_dir / "chain.crt",
    )


def ensure_certificates(cert_dir: Path, openssl: str = "openssl") -> CertPaths:
    """Return the certificate paths, generating CA and leaf on first use."""
    paths = cert_paths(cert_dir)
    if paths.chain.is_file() and paths.leaf_key.is_file():
        return paths
    _LOGGER.info("Generating local CA and certificate in %s", cert_dir)
    cert_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cert_dir) as tmp_name:
        tmp = Path(tmp_name)
        _generate(tmp, openssl)
        for name in ("ca.key", "ca.crt", "server.key", "server.crt", "chain.crt"):
            os.replace(tmp / name, cert_dir / name)
    for key in (cert_dir / "ca.key", paths.leaf_key):
        key.chmod(0o600)
    return paths


def _generate(tmp: Path, openssl: str) -> None:
    if shutil.which(openssl) is None:
        raise RuntimeError(f"{openssl!r} not found; it is needed to create certificates")

    def run(*args: str) -> None:
        subprocess.run([openssl, *args], cwd=tmp, check=True, capture_output=True)

    days = str(VALIDITY_DAYS)
    run(
        "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-sha256", "-days", days,
        "-subj", "/CN=SYR Local CA",
        "-addext", "basicConstraints=critical,CA:TRUE",
        "-addext", "keyUsage=critical,keyCertSign,cRLSign",
        "-keyout", "ca.key", "-out", "ca.crt",
    )
    run(
        "req", "-new", "-newkey", "rsa:2048", "-nodes", "-sha256",
        "-subj", "/CN=syrconnect.de",
        "-keyout", "server.key", "-out", "server.csr",
    )
    (tmp / "leaf.ext").write_text(
        f"subjectAltName={LEAF_SANS}\n"
        "basicConstraints=CA:FALSE\n"
        "keyUsage=critical,digitalSignature,keyEncipherment\n"
        "extendedKeyUsage=serverAuth\n",
        encoding="ascii",
    )
    run(
        "x509", "-req", "-in", "server.csr", "-CA", "ca.crt", "-CAkey", "ca.key",
        "-CAcreateserial", "-sha256", "-days", days, "-extfile", "leaf.ext",
        "-out", "server.crt",
    )
    (tmp / "chain.crt").write_bytes((tmp / "server.crt").read_bytes() + (tmp / "ca.crt").read_bytes())


def server_tls_context(paths: CertPaths) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.set_ciphers(CIPHERS)
    context.load_cert_chain(paths.chain, paths.leaf_key)
    return context
