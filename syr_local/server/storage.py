"""Persist the device identity (never readings) across add-on restarts."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from .mapping import Identity, valid_serial

_LOGGER = logging.getLogger(__name__)


def load_identity(path: Path) -> Identity:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Identity()
    except (OSError, ValueError) as err:
        _LOGGER.warning("Ignoring unreadable %s: %s", path, err)
        return Identity()
    if not isinstance(data, dict):
        return Identity()
    model = data.get("model")
    return Identity(
        serial=valid_serial(data.get("serial")),
        model=model if isinstance(model, str) and model else None,
    )


def save_identity(path: Path, identity: Identity) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"serial": identity.serial, "model": identity.model}), encoding="utf-8"
    )
    os.replace(tmp, path)
