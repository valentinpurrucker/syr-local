"""Serve the bundled dashboard card and load it in the frontend."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Final

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN

CARD_URL: Final = f"/{DOMAIN}/syr-local-card.js"
CARD_PATH: Final = Path(__file__).parent / "frontend" / "syr-local-card.js"


def card_digest(path: Path = CARD_PATH) -> str:
    """Short content hash of the card file, used to bust browser caches."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


async def async_register_card(hass: HomeAssistant) -> None:
    """Serve the card file and add it to every frontend page load.

    The URL carries a hash of the file contents, so browsers fetch the card
    again whenever it changes, even if the version number stays the same.
    """
    digest = await hass.async_add_executor_job(card_digest)
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(CARD_PATH), cache_headers=True)]
    )
    add_extra_js_url(hass, f"{CARD_URL}?v={digest}")
