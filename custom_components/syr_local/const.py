"""Constants for the SYR Local integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "syr_local"

DEFAULT_HOST: Final = "local-syr-local"
DEFAULT_PORT: Final = 8099

UPDATE_INTERVAL: Final = timedelta(seconds=30)
REQUEST_TIMEOUT_S: Final = 10
# The device polls every ~11 s; no contact for this long means it is offline.
DEVICE_STALE_AFTER: Final = timedelta(minutes=5)
