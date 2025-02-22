"""Binary sensor platform for Victor Smart-Kill."""
import logging
from typing import Callable, Iterable, List, Optional

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import HomeAssistantType
from victor_smart_kill import Trap

from custom_components.victorsmartkill import IntegrationContext
from custom_components.victorsmartkill.const import (
    ATTR_LAST_KILL_DATE,
    DOMAIN,
    ICON_CAPTURED,
)
from custom_components.victorsmartkill.entity import VictorSmartKillEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistantType,
    entry: ConfigEntry,
    async_add_entities: Callable[[Iterable[Entity], Optional[bool]], None],
) -> None:
    """Set up binary_sensor platform."""
    context: IntegrationContext = hass.data[DOMAIN][entry.entry_id]
    traps: List[Trap] = context.coordinator.data

    entities = []
    for trap in traps:
        entities.extend([VictorSmartKillBinarySensor(trap.id, context.coordinator)])
        _LOGGER.debug(
            "Add %s binary sensors for trap named '%s' with Victor trap id %d.",
            [f"{type(entity).__name__}" for entity in entities],
            trap.name,
            trap.id,
        )

    async_add_entities(entities, False)


class VictorSmartKillBinarySensor(VictorSmartKillEntity, BinarySensorEntity):
    """Victor Smart-Kill occupancy binary sensor class."""

    @property
    def _exclude_extra_state_attributes(self) -> List[str]:
        return [ATTR_LAST_KILL_DATE]

    @property
    def _name_suffix(self) -> str:
        return "capture"

    @property
    def _unique_id_suffix(self) -> str:
        return "capture"

    @property
    def device_class(self) -> str:
        """Return the class of this binary_sensor."""
        return "occupancy"

    @property
    def is_on(self) -> bool:
        """Return true if the binary_sensor is on."""
        return self.trap.trapstatistics.kills_present > 0

    @property
    def icon(self) -> str:
        """Return the icon of the sensor."""
        return ICON_CAPTURED
