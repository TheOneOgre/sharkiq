"""Coordinator to manage Shark IQ updates."""
from __future__ import annotations

from datetime import timedelta
from typing import Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_REGION, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    AUTH0_REFRESH_TOKEN_KEY,
    DOMAIN,
    LOGGER,
    SHARKIQ_REGION_EUROPE,
    UPDATE_INTERVAL,
)
from .sharkiq import SharkIqAuthError, SharkIqVacuum, get_ayla_api


class SharkIqUpdateCoordinator(DataUpdateCoordinator[Dict[str, SharkIqVacuum]]):
    """Class to manage fetching Shark IQ data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name="Shark IQ devices",
            update_interval=UPDATE_INTERVAL,
        )
        self.entry = entry
        self.shark_vacs: Dict[str, SharkIqVacuum] = {}
        self._ayla_api = None
        self._region_eu = entry.data.get(CONF_REGION) == SHARKIQ_REGION_EUROPE
        self._online_serials: set[str] = set()

    async def _async_create_api(self):
        """Create or return Ayla API client."""
        if self._ayla_api:
            return self._ayla_api
        session = async_get_clientsession(self.hass)
        self._ayla_api = get_ayla_api(
            username=self.entry.data[CONF_USERNAME],
            password=self.entry.data[CONF_PASSWORD],
            websession=session,
            europe=self._region_eu,
            auth0_refresh_token=self.entry.data.get(AUTH0_REFRESH_TOKEN_KEY),
        )
        return self._ayla_api

    async def _async_update_data(self) -> Dict[str, SharkIqVacuum]:
        """Fetch data from Shark IQ."""
        api = await self._async_create_api()
        try:
            await api.async_sign_in()
            devices = await api.async_get_devices(update=True)
        except SharkIqAuthError as err:
            raise UpdateFailed(f"Auth failed: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Error fetching Shark IQ data: {err}") from err

        # Return devices keyed by serial for easy lookups.
        # Cache for platform access
        self.shark_vacs = {device.serial_number: device for device in devices}
        # Mark any device we successfully fetched as online for this cycle
        self._online_serials = {device.serial_number for device in devices}

        def _mask_sn(sn: str) -> str:
            # Hide most of the serial for logs
            if not sn or len(sn) < 4:
                return "***"
            return f"{sn[:2]}***{sn[-2:]}"

        for device in devices:
            LOGGER.debug(
                "Device %s (%s) product=%s oem_model=%s connection_status=%s error_code=%s properties=%s",
                device.name,
                _mask_sn(device.serial_number),
                device.name,
                device.oem_model_number,
                getattr(device, "connection_status", "unknown"),
                device.error_code,
                ", ".join(sorted(device.properties_full.keys())),
            )

        return self.shark_vacs

    def device_is_online(self, serial_number: str) -> bool:
        """Return True if the device is online, False otherwise.

        Heuristic: if we successfully refreshed this serial in the current cycle,
        treat it as online even if the listing said Offline.
        """
        if serial_number in self._online_serials:
            return True
        device = self.shark_vacs.get(serial_number)
        if device is None:
            LOGGER.debug(
                "Requested online status for unknown Shark IQ device %s", serial_number
            )
            return False

        # Fallback to connection_status flag from the API listing.
        return getattr(device, "connection_status", "").lower() != "offline"
