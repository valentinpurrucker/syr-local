"""Data update coordinator for SYR Local."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import CannotConnectError, SyrLocalClient
from .const import DEVICE_STALE_AFTER, DOMAIN, UPDATE_INTERVAL
from .models import InvalidStateError, SyrLocalState, UnsupportedVersionError

_LOGGER = logging.getLogger(__name__)

type SyrLocalConfigEntry = ConfigEntry[SyrLocalCoordinator]


class SyrLocalCoordinator(DataUpdateCoordinator[SyrLocalState]):
    """Poll the add-on's state API."""

    config_entry: SyrLocalConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: SyrLocalConfigEntry, client: SyrLocalClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> SyrLocalState:
        try:
            state = await self.client.async_get_state()
        except CannotConnectError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="cannot_connect"
            ) from err
        except UnsupportedVersionError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="unsupported_version"
            ) from err
        except InvalidStateError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="invalid_response"
            ) from err

        expected = self.config_entry.unique_id
        actual = state.device.serial
        if expected and actual and actual != expected:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="wrong_device"
            )
        return state

    @property
    def device_online(self) -> bool:
        """True if the device contacted the add-on within the last five minutes."""
        if not self.last_update_success or self.data is None:
            return False
        last_seen = self.data.last_seen
        return last_seen is not None and dt_util.utcnow() - last_seen <= DEVICE_STALE_AFTER
