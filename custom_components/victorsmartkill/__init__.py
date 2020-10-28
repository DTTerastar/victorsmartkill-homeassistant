"""
Custom integration to integrate victorsmartkill with Home Assistant.

For more details about this integration, please refer to
https://github.com/toreamun/victorsmartkill-homeassistant
"""
import asyncio
from datetime import timedelta
import logging
from typing import Callable, List

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Config, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.typing import EventType, HomeAssistantType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from victor_smart_kill import Trap, VictorApi, VictorAsyncClient

from custom_components.victorsmartkill.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
    EVENT_TRAP_LIST_CHANGED,
    PLATFORMS,
    STARTUP_MESSAGE,
)

SCAN_INTERVAL = timedelta(minutes=5)

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistantType, config: Config) -> bool:
    """Set up this integration using YAML is not supported."""
    # pylint: disable=unused-argument
    return True


async def async_setup_entry(hass: HomeAssistantType, entry: ConfigEntry) -> bool:
    """Set up this integration using UI."""
    _LOGGER.debug(
        "Setup entry %s %s with scan interval %s.",
        entry.domain,
        entry.title,
        SCAN_INTERVAL,
    )

    if hass.data.get(DOMAIN) is None:
        hass.data.setdefault(DOMAIN, {})
        _LOGGER.info(STARTUP_MESSAGE)

    username = entry.data.get(CONF_USERNAME)
    password = entry.data.get(CONF_PASSWORD)

    coordinator = VictorSmartKillDataUpdateCoordinator(
        hass,
        SCAN_INTERVAL,
        username=username,
        password=password,
    )
    await coordinator.async_refresh()

    if not coordinator.last_update_success:
        raise ConfigEntryNotReady

    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Forward setup to each platform
    for platform in PLATFORMS:
        if entry.options.get(platform, True):
            coordinator.platforms.append(platform)
            # Use `hass.async_create_task` (not async_add_job) to avoid a circular
            # dependency between the platform and the component
            hass.async_create_task(
                hass.config_entries.async_forward_entry_setup(entry, platform)
            )

    entry.add_update_listener(async_reload_entry)

    @callback
    async def async_trap_list_changed(event: EventType):
        _LOGGER.info(
            "Trap list hast changed (%s), reload integration entry.", event.data
        )
        await async_reload_entry(hass, entry)

    hass.bus.async_listen_once(EVENT_TRAP_LIST_CHANGED, async_trap_list_changed)

    return True


class VictorSmartKillDataUpdateCoordinator(DataUpdateCoordinator[List[Trap]]):
    """Class to manage fetching data from the API."""

    def __init__(
        self,
        hass: HomeAssistantType,
        update_interval: timedelta,
        username: str,
        password: str,
    ) -> None:
        """Initialize."""
        self._client = VictorAsyncClient(username, password)
        self._api = VictorApi(self._client)
        self.platforms: List[str] = []  # appended from async_setup_entry

        super().__init__(
            hass,
            _LOGGER,
            update_method=self.async_update_data,
            name=DOMAIN,
            update_interval=update_interval,
        )

    async def async_close(self) -> None:
        """Close resources."""
        self.logger.debug("Close API client.")
        await self._client.aclose()

    @callback
    def async_add_listener(
        self, update_callback: Callable[[], None]
    ) -> Callable[[], None]:
        """Listen for data updates. Called by CoordinatorEntity."""
        try:
            return super().async_add_listener(update_callback)
        except Exception:
            self.logger.debug("async_add_listener() failed", exc_info=True)
            raise
        self.logger.debug(
            "async_add_listener() called.",
        )

    async def async_refresh(self) -> None:
        """Refresh data."""
        try:
            await super().async_refresh()
        except Exception:
            self.logger.debug("async_refresh() failed", exc_info=True)
            raise
        self.logger.debug(
            "async_refresh() done, last_update_success is %s", self.last_update_success
        )

    async def async_update_data(self) -> List[Trap]:
        """Update data via Victor Smart-Kill API."""
        self.logger.debug(
            "async_update_data running for %s, currently coordinating %d listeners.",
            type(self).__name__,
            len(self._listeners),
        )

        try:
            if not self.data:
                traps = await self._get_traps()
            else:
                previous_trap_ids = sorted([trap.id for trap in self.data])
                traps = await self._get_traps()
                current_trap_ids = sorted([trap.id for trap in traps])
                if previous_trap_ids != current_trap_ids:
                    self.logger.debug(
                        "List of traps has changed from %s to %s.",
                        previous_trap_ids,
                        current_trap_ids,
                    )

                    self.hass.bus.async_fire(
                        EVENT_TRAP_LIST_CHANGED,
                        event_data={
                            "previous_traps": previous_trap_ids,
                            "current_traps": current_trap_ids,
                        },
                    )
            return traps
        except Exception as exception:
            raise UpdateFailed(exception) from exception

    async def _get_traps(self) -> List[Trap]:
        """Get list of traps from API."""
        try:
            traps = await self._api.get_traps()
            self.logger.debug(
                "Received traps %s from Victor Smart-Kill API.",
                sorted([trap.id for trap in traps]),
            )
            return traps
        except Exception:
            self.logger.debug(
                "Error getting traps from Victor Smart-Kill API.", exc_info=True
            )
            raise


async def async_unload_entry(hass: HomeAssistantType, entry: ConfigEntry):
    """Handle removal of an entry."""
    _LOGGER.debug("Unload entry %s %s.", entry.domain, entry.title)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    unloaded = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, platform)
                for platform in PLATFORMS
                if platform in coordinator.platforms
            ]
        )
    )
    if unloaded:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        if coordinator:
            await coordinator.async_close()

    return unloaded


async def async_reload_entry(hass: HomeAssistantType, entry: ConfigEntry):
    """Reload entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
