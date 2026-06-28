"""Const for Midea Lan."""

from enum import IntEnum

from homeassistant.const import Platform

DOMAIN = "midea_ac_lan"
COMPONENT = "component"
DEVICES = "devices"

CONF_KEY = "key"
CONF_MODEL = "model"
CONF_SUBTYPE = "subtype"
CONF_ACCOUNT = "account"
CONF_SERVER = "server"
CONF_REFRESH_INTERVAL = "refresh_interval"

CONF_EXTERNAL_TEMP_SENSOR = "external_temp_sensor"
CONF_FOLLOW_ME_ENABLED = "follow_me_enabled"
CONF_FOLLOW_ME_INTERVAL = "follow_me_interval"

DEFAULT_FOLLOW_ME_INTERVAL = 120
FOLLOW_ME_GRACE_PERIOD = 300
FOLLOW_ME_COORDINATORS = "follow_me_coordinators"
FOLLOW_ME_ENTITIES = "follow_me_entities"

EXTRA_SENSOR = [Platform.SENSOR, Platform.BINARY_SENSOR]
EXTRA_SWITCH = [Platform.SWITCH, Platform.LOCK, Platform.SELECT, Platform.NUMBER]
EXTRA_CONTROL = [
    Platform.CLIMATE,
    Platform.WATER_HEATER,
    Platform.FAN,
    Platform.HUMIDIFIER,
    Platform.LIGHT,
    *EXTRA_SWITCH,
]
ALL_PLATFORM = EXTRA_SENSOR + EXTRA_CONTROL


class FanSpeed(IntEnum):
    """FanSpeed reference values."""

    LOW = 20
    MEDIUM = 40
    HIGH = 60
    FULL_SPEED = 80
    AUTO = 100
