"""Client for the SYR Local add-on state API (read-only, GET only)."""

from __future__ import annotations

import aiohttp
from yarl import URL

from .const import REQUEST_TIMEOUT_S
from .models import InvalidStateError, SyrLocalError, SyrLocalState, parse_state

STATE_PATH = "/api/v1/state"


class CannotConnectError(SyrLocalError):
    """The add-on could not be reached."""


def state_url(host: str, port: int) -> URL:
    # URL.build brackets IPv6 literals such as "fd00::1".
    return URL.build(scheme="http", host=host, port=port, path=STATE_PATH)


class SyrLocalClient:
    def __init__(self, session: aiohttp.ClientSession, host: str, port: int) -> None:
        self._session = session
        self.url = state_url(host, port)

    async def async_get_state(self) -> SyrLocalState:
        try:
            async with self._session.get(
                self.url, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_S)
            ) as response:
                if response.status != 200:
                    raise InvalidStateError(f"HTTP {response.status} from {self.url}")
                payload = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnectError(f"cannot reach {self.url}: {err}") from err
        except ValueError as err:
            raise InvalidStateError(f"invalid JSON from {self.url}") from err
        return parse_state(payload)
