"""Follow Me coordinator — report external temperature to AC over LAN."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE_ID, STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util
from midealocal.device import DeviceType
from midealocal.devices.ac import MideaACDevice

from .const import (
    CONF_EXTERNAL_TEMP_SENSOR,
    CONF_FOLLOW_ME_ENABLED,
    CONF_FOLLOW_ME_INTERVAL,
    DEFAULT_FOLLOW_ME_INTERVAL,
    DEVICES,
    DOMAIN,
    FOLLOW_ME_COORDINATORS,
    FOLLOW_ME_ENTITIES,
    FOLLOW_ME_GRACE_PERIOD,
)

_LOGGER = logging.getLogger(__name__)


def _follow_me_enabled(options: dict[str, Any]) -> bool:
    return bool(options.get(CONF_FOLLOW_ME_ENABLED))


def _external_sensor(options: dict[str, Any]) -> str | None:
    sensor = options.get(CONF_EXTERNAL_TEMP_SENSOR)
    if not sensor:
        return None
    return str(sensor)


def _follow_me_interval(options: dict[str, Any]) -> int:
    interval = options.get(CONF_FOLLOW_ME_INTERVAL, DEFAULT_FOLLOW_ME_INTERVAL)
    try:
        return max(60, min(180, int(interval)))
    except (TypeError, ValueError):
        return DEFAULT_FOLLOW_ME_INTERVAL


def _temperature_celsius(hass: HomeAssistant, entity_id: str) -> float | None:
    state = hass.states.get(entity_id)
    if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None
    try:
        value = float(state.state)
    except (TypeError, ValueError):
        return None
    if state.attributes.get("unit_of_measurement") == UnitOfTemperature.FAHRENHEIT:
        return (value - 32) * 5 / 9
    return value


class FollowMeCoordinator:
    """Send Follow Me enable + periodic external temperature to the AC."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        device: MideaACDevice,
    ) -> None:
        self.hass = hass
        self.config_entry = config_entry
        self.device = device
        self._unsub_sensor: callback | None = None
        self._unsub_interval: callback | None = None
        self._unsub_device: callback | None = None
        self._grace_unsub: callback | None = None
        self._power_off_at: datetime | None = None
        self._enabled = False

    async def async_setup(self) -> None:
        """Start Follow Me if configured."""
        await self.async_unload()
        options = self.config_entry.options
        sensor_id = _external_sensor(options)
        if not _follow_me_enabled(options) or not sensor_id:
            return

        self._enabled = True
        _LOGGER.debug(
            "Setting up Follow Me for device %s using sensor %s",
            self.device.device_id,
            sensor_id,
        )

        await self.hass.async_add_executor_job(self.device.enable_follow_me)

        @callback
        def _on_sensor_event(event: Any) -> None:  # noqa: ANN401
            self.hass.async_create_task(self._async_report(force=True))

        self._unsub_sensor = async_track_state_change_event(
            self.hass,
            [sensor_id],
            _on_sensor_event,
        )

        interval = timedelta(seconds=_follow_me_interval(options))

        @callback
        def _on_interval(now: datetime) -> None:
            self.hass.async_create_task(self._async_report())

        self._unsub_interval = async_track_time_interval(
            self.hass,
            _on_interval,
            interval,
        )

        @callback
        def _on_device_update(status: dict[str, Any]) -> None:
            if "power" not in status:
                return
            if status["power"]:
                self._power_off_at = None
                if self._grace_unsub:
                    self._grace_unsub()
                    self._grace_unsub = None
            elif self._power_off_at is None:
                self._power_off_at = dt_util.utcnow()
                self._schedule_grace_stop()

        self.device.register_update(_on_device_update)
        self._unsub_device = lambda: self.device.unregister_update(_on_device_update)

        await self._async_report(force=True)

    def _schedule_grace_stop(self) -> None:
        if self._grace_unsub:
            self._grace_unsub()

        @callback
        def _grace_elapsed(_now: datetime) -> None:
            self._grace_unsub = None
            _LOGGER.debug(
                "Follow Me grace period ended for device %s",
                self.device.device_id,
            )

        self._grace_unsub = async_call_later(
            self.hass,
            FOLLOW_ME_GRACE_PERIOD,
            _grace_elapsed,
        )

    async def _async_report(self, *, force: bool = False) -> None:
        if not self._enabled:
            return

        options = self.config_entry.options
        sensor_id = _external_sensor(options)
        if not sensor_id:
            return

        power = bool(self.device.get_attribute("power"))
        if not power:
            if self._power_off_at is None:
                return
            elapsed = (dt_util.utcnow() - self._power_off_at).total_seconds()
            if elapsed > FOLLOW_ME_GRACE_PERIOD:
                return

        temp_c = _temperature_celsius(self.hass, sensor_id)
        if temp_c is None:
            _LOGGER.debug(
                "Follow Me skip for device %s: sensor %s unavailable",
                self.device.device_id,
                sensor_id,
            )
            return

        _LOGGER.debug(
            "Follow Me reporting %.1f °C to device %s (force=%s)",
            temp_c,
            self.device.device_id,
            force,
        )
        await self.hass.async_add_executor_job(
            self.device.report_follow_me_temperature,
            temp_c,
        )
        self._refresh_display_entities()

    def _refresh_display_entities(self) -> None:
        entities = (
            self.hass.data.get(DOMAIN, {})
            .get(FOLLOW_ME_ENTITIES, {})
            .get(self.device.device_id, {})
        )
        for entity in entities.values():
            entity.async_write_ha_state()

    async def async_unload(self) -> None:
        """Stop listeners and timers."""
        self._enabled = False
        if self._unsub_sensor:
            self._unsub_sensor()
            self._unsub_sensor = None
        if self._unsub_interval:
            self._unsub_interval()
            self._unsub_interval = None
        if self._unsub_device:
            self._unsub_device()
            self._unsub_device = None
        if self._grace_unsub:
            self._grace_unsub()
            self._grace_unsub = None
        self._power_off_at = None


async def async_setup_follow_me(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    device: MideaACDevice,
) -> None:
    """Set up Follow Me for an AC config entry."""
    if device.device_type != DeviceType.AC:
        return
    coordinator = FollowMeCoordinator(hass, config_entry, device)
    hass.data[DOMAIN].setdefault(FOLLOW_ME_COORDINATORS, {})[
        config_entry.entry_id
    ] = coordinator
    await coordinator.async_setup()


async def async_unload_follow_me(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> None:
    """Unload Follow Me for a config entry."""
    coordinators = hass.data.get(DOMAIN, {}).get(FOLLOW_ME_COORDINATORS, {})
    coordinator = coordinators.pop(config_entry.entry_id, None)
    if coordinator:
        await coordinator.async_unload()


async def async_reload_follow_me(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> None:
    """Reload Follow Me after options change."""
    device_id = config_entry.data.get(CONF_DEVICE_ID)
    device = hass.data.get(DOMAIN, {}).get(DEVICES, {}).get(device_id)
    if device is None or device.device_type != DeviceType.AC:
        await async_unload_follow_me(hass, config_entry)
        return
    await async_unload_follow_me(hass, config_entry)
    await async_setup_follow_me(hass, config_entry, device)


def get_follow_me_external_temperature(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> float | None:
    """Return external sensor temperature when Follow Me display override is active."""
    options = config_entry.options
    if not _follow_me_enabled(options):
        return None
    sensor_id = _external_sensor(options)
    if not sensor_id:
        return None
    return _temperature_celsius(hass, sensor_id)
