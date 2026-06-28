"""Sensor for Midea Lan."""

from typing import Any, cast

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE_ID, CONF_SENSORS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from midealocal.device import MideaDevice

from .const import DEVICES, DOMAIN, FOLLOW_ME_ENTITIES
from .follow_me import get_follow_me_external_temperature
from .midea_devices import MIDEA_DEVICES
from .midea_entity import MideaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors for device."""
    device_id = config_entry.data.get(CONF_DEVICE_ID)
    device = hass.data[DOMAIN][DEVICES].get(device_id)
    extra_sensors = config_entry.options.get(CONF_SENSORS, [])
    sensors = []
    for entity_key, config in cast(
        "dict",
        MIDEA_DEVICES[device.device_type]["entities"],
    ).items():
        if config["type"] == Platform.SENSOR and entity_key in extra_sensors:
            sensor = MideaSensor(device, entity_key, config_entry)
            sensors.append(sensor)
    async_add_entities(sensors)


class MideaSensor(MideaEntity, SensorEntity):
    """Represent a Midea  sensor."""

    def __init__(
        self,
        device: MideaDevice,
        entity_key: str,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize Midea sensor."""
        super().__init__(device, entity_key)
        self._config_entry = config_entry

    async def async_added_to_hass(self) -> None:
        """Register indoor temperature sensor for Follow Me display refresh."""
        await super().async_added_to_hass()
        if self._entity_key == "indoor_temperature":
            self.hass.data.setdefault(DOMAIN, {}).setdefault(
                FOLLOW_ME_ENTITIES,
                {},
            ).setdefault(self._device.device_id, {})[
                "indoor_temperature"
            ] = self

    @property
    def native_value(self) -> StateType:
        """Return entity value."""
        if self._entity_key == "indoor_temperature":
            external = get_follow_me_external_temperature(
                self.hass,
                self._config_entry,
            )
            if external is not None:
                return external
        return cast("StateType", self._device.get_attribute(self._entity_key))

    @property
    def device_class(self) -> SensorDeviceClass:
        """Return device class."""
        return cast("SensorDeviceClass", self._config.get("device_class"))

    @property
    def state_class(self) -> SensorStateClass | None:
        """Return state state."""
        return cast("SensorStateClass | None", self._config.get("state_class"))

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return unit of measurement."""
        return cast("str | None", self._config.get("unit"))

    @property
    def capability_attributes(self) -> dict[str, Any] | None:
        """Return capabilities."""
        return {"state_class": self.state_class} if self.state_class else {}
