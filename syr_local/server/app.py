"""Add-on entrypoint: wire configuration, servers and discovery together."""

from __future__ import annotations

import logging
import logging.handlers
import os
import signal
import sys
import threading
from datetime import UTC, datetime, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .catalog import FULL_GETTERS
from .certs import ensure_certificates, server_tls_context
from .config import Config, ConfigError, load_config
from .device_server import DeviceContext, DeviceServer
from .discovery import DiscoveryAnnouncer
from .mapping import Identity
from .planner import CommandPlanner
from .state import DeviceState
from .state_api import StateServer
from .storage import load_identity, save_identity

_LOGGER = logging.getLogger("syr_local")

REQUEST_LOG_BYTES = 1024 * 1024
REQUEST_LOG_BACKUPS = 2


def main() -> int:
    try:
        config = load_config()
    except ConfigError as err:
        logging.basicConfig(level=logging.ERROR)
        _LOGGER.error("Invalid configuration: %s", err)
        return 2
    _setup_logging(config.log_level)

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    run(config, stop)
    return 0


def run(config: Config, stop: threading.Event) -> None:
    tz = _device_timezone()
    identity_file = config.data_dir / "identity.json"
    state = DeviceState(datetime.now(UTC), load_identity(identity_file))
    announcer = DiscoveryAnnouncer(os.environ.get("SUPERVISOR_TOKEN"), config.state_port)

    def on_identity(identity: Identity) -> None:
        _LOGGER.info("Device identified: serial %s, model %s", identity.serial, identity.model)
        try:
            save_identity(identity_file, identity)
        except OSError as err:
            _LOGGER.warning("Cannot persist identity: %s", err)
        if identity.serial:
            announcer.announce(identity.serial)

    context = DeviceContext(
        config=config,
        state=state,
        planner=CommandPlanner(config.poll_interval),
        on_identity=on_identity,
        request_log=_request_logger(config) if config.log_requests else None,
    )
    tls = server_tls_context(ensure_certificates(config.cert_dir))
    device_server = DeviceServer((config.bind_host, config.device_port), context, tls)
    state_server = StateServer((config.bind_host, config.state_port), state, tz)

    threads = [
        threading.Thread(target=device_server.serve_forever, name="device", daemon=True),
        threading.Thread(target=state_server.serve_forever, name="state-api", daemon=True),
    ]
    for thread in threads:
        thread.start()
    _LOGGER.info(
        "SYR Local (read-only) listening: device TLS on %s:%s, state API on %s:%s",
        config.bind_host, config.device_port, config.bind_host, config.state_port,
    )
    _LOGGER.info(
        "Requesting %d getters at most every %d s; set* and getSIR are refused; "
        "firmware and maintenance requests get 404",
        len(FULL_GETTERS), config.poll_interval,
    )
    if known := state.identity().serial:
        announcer.announce(known)

    stop.wait()
    _LOGGER.info("Shutting down")
    announcer.stop()
    device_server.shutdown()
    state_server.shutdown()
    device_server.server_close()
    state_server.server_close()


def _device_timezone() -> tzinfo:
    # The Supervisor passes the Home Assistant time zone as TZ. The device
    # reports local wall time, so this zone is used to convert getLAR to UTC.
    name = os.environ.get("TZ")
    if not name:
        return UTC
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        _LOGGER.warning("Unknown time zone %r; treating device times as UTC", name)
        return UTC


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        stream=sys.stdout,
        level=level.upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def _request_logger(config: Config) -> logging.Logger:
    # Raw bodies contain the serial and MAC; only written when log_requests is on.
    logger = logging.getLogger("syr_local.requests")
    logger.propagate = False
    logger.setLevel(logging.INFO)
    handler = logging.handlers.RotatingFileHandler(
        config.data_dir / "requests.log",
        maxBytes=REQUEST_LOG_BYTES,
        backupCount=REQUEST_LOG_BACKUPS,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    _LOGGER.info("Logging raw device requests to %s", config.data_dir / "requests.log")
    return logger
