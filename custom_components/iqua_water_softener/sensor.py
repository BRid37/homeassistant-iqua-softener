import logging
from datetime import datetime, timedelta
from typing import Optional

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import (  
    CoordinatorEntity,  
    DataUpdateCoordinator,  
    UpdateFailed
)
from homeassistant.components.sensor import (  
    SensorEntity,  
    SensorEntityDescription,  
    SensorDeviceClass,  
    SensorStateClass
)
from homeassistant.const import PERCENTAGE, UnitOfVolume
from homeassistant.config_entries import ConfigEntry

from .const import (  
    DOMAIN,  
    CONF_USERNAME,  
    CONF_PASSWORD,  
    CONF_DEVICE_SERIAL_NUMBER,  
    VOLUME_FLOW_RATE_LITERS_PER_MINUTE,  
    VOLUME_FLOW_RATE_GALLONS_PER_MINUTE
)

from iqua_softener import (  
    IquaSoftener,  
    IquaSoftenerData,  
    IquaSoftenerVolumeUnit,  
    IquaSoftenerException
)

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(minutes=15)

PLATFORMS = ["sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    config = hass.data[DOMAIN][entry.entry_id]
    if entry.options:
        config.update(entry.options)

    device_serial_number = config[CONF_DEVICE_SERIAL_NUMBER]
    coordinator = IquaSoftenerCoordinator(
        hass,
        IquaSoftener(
            config[CONF_USERNAME],
            config[CONF_PASSWORD],
            device_serial_number
        )
    )
    await coordinator.async_config_entry_first_refresh()

    SENSOR_TYPES = [
        (IquaSoftenerStateSensor, SensorEntityDescription(key="State", name="State")),
        (IquaSoftenerDeviceDateTimeSensor, SensorEntityDescription(key="DATE_TIME", name="Date/time", icon="mdi:clock")),
        (IquaSoftenerLastRegenerationSensor, SensorEntityDescription(key="LAST_REGENERATION", name="Last regeneration", device_class=SensorDeviceClass.TIMESTAMP)),
        (IquaSoftenerOutOfSaltEstimatedDaySensor, SensorEntityDescription(key="OUT_OF_SALT_ESTIMATED_DAY", name="Out of salt estimated day", device_class=SensorDeviceClass.TIMESTAMP)),
        (IquaSoftenerSaltLevelSensor, SensorEntityDescription(key="SALT_LEVEL", name="Salt level", state_class=SensorStateClass.MEASUREMENT, native_unit_of_measurement=PERCENTAGE)),
        (IquaSoftenerAvailableWaterSensor, SensorEntityDescription(key="AVAILABLE_WATER", name="Available water", state_class=SensorStateClass.TOTAL, device_class=SensorDeviceClass.WATER, icon="mdi:water")),
        (IquaSoftenerWaterCurrentFlowSensor, SensorEntityDescription(key="WATER_CURRENT_FLOW", name="Water current flow", state_class=SensorStateClass.MEASUREMENT, icon="mdi:water-pump")),
        (IquaSoftenerWaterUsageTodaySensor, SensorEntityDescription(key="WATER_USAGE_TODAY", name="Today water usage", state_class=SensorStateClass.TOTAL_INCREASING, device_class=SensorDeviceClass.WATER, icon="mdi:water-minus")),
        (IquaSoftenerWaterUsageDailyAverageSensor, SensorEntityDescription(key="WATER_USAGE_DAILY_AVERAGE", name="Water usage daily average", state_class=SensorStateClass.MEASUREMENT, device_class=SensorDeviceClass.WATER)),
    ]

    async_add_entities([
        sensor_cls(coordinator, device_serial_number, description)
        for sensor_cls, description in SENSOR_TYPES
    ])

class IquaSoftenerCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, softener: IquaSoftener):
        super().__init__(
            hass,
            _LOGGER,
            name="Iqua Softener",
            update_interval=UPDATE_INTERVAL
        )
        self.softener = softener

    async def _async_update_data(self) -> IquaSoftenerData:
        try:
            return await self.hass.async_add_executor_job(self.softener.get_data)
        except IquaSoftenerException as err:
            raise UpdateFailed(f"Failed to fetch IQua softener data: {err}")

class IquaSoftenerSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator: IquaSoftenerCoordinator, serial: str, description: SensorEntityDescription):
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{serial}_{description.key}".lower()

class IquaSoftenerStateSensor(IquaSoftenerSensor):
    @property
    def native_value(self):
        return str(self.coordinator.data.state.value)

class IquaSoftenerDeviceDateTimeSensor(IquaSoftenerSensor):
    @property
    def native_value(self):
        return self.coordinator.data.device_date_time.strftime("%Y-%m-%d %H:%M:%S")

class IquaSoftenerLastRegenerationSensor(IquaSoftenerSensor):
    @property
    def native_value(self):
        dt = self.coordinator.data.device_date_time
        return (datetime.now(dt.tzinfo) - timedelta(days=self.coordinator.data.days_since_last_regeneration)).replace(hour=0, minute=0, second=0)

class IquaSoftenerOutOfSaltEstimatedDaySensor(IquaSoftenerSensor):
    @property
    def native_value(self):
        dt = self.coordinator.data.device_date_time
        return (datetime.now(dt.tzinfo) + timedelta(days=self.coordinator.data.out_of_salt_estimated_days)).replace(hour=0, minute=0, second=0)

class IquaSoftenerSaltLevelSensor(IquaSoftenerSensor):
    @property
    def native_value(self):
        return self.coordinator.data.salt_level_percent

    @property
    def icon(self) -> Optional[str]:
        value = self.native_value
        if value is None:
            return "mdi:signal"
        if value > 75:
            return "mdi:signal-cellular-3"
        elif value > 50:
            return "mdi:signal-cellular-2"
        elif value > 25:
            return "mdi:signal-cellular-1"
        elif value > 5:
            return "mdi:signal-cellular-outline"
        return "mdi:signal-off"

class IquaSoftenerAvailableWaterSensor(IquaSoftenerSensor):
    @property
    def native_value(self):
        value = self.coordinator.data.total_water_available
        return value / 1000 if self.coordinator.data.volume_unit == IquaSoftenerVolumeUnit.LITERS else value

    @property
    def native_unit_of_measurement(self):
        return UnitOfVolume.CUBIC_METERS if self.coordinator.data.volume_unit == IquaSoftenerVolumeUnit.LITERS else UnitOfVolume.GALLONS

    @property
    def last_reset(self):
        return datetime.now(self.coordinator.data.device_date_time.tzinfo) - timedelta(days=self.coordinator.data.days_since_last_regeneration)

class IquaSoftenerWaterCurrentFlowSensor(IquaSoftenerSensor):
    @property
    def native_value(self):
        return self.coordinator.data.current_water_flow

    @property
    def native_unit_of_measurement(self):
        return VOLUME_FLOW_RATE_LITERS_PER_MINUTE if self.coordinator.data.volume_unit == IquaSoftenerVolumeUnit.LITERS else VOLUME_FLOW_RATE_GALLONS_PER_MINUTE

class IquaSoftenerWaterUsageTodaySensor(IquaSoftenerSensor):
    @property
    def native_value(self):
        value = self.coordinator.data.today_use
        return value / 1000 if self.coordinator.data.volume_unit == IquaSoftenerVolumeUnit.LITERS else value

    @property
    def native_unit_of_measurement(self):
        return UnitOfVolume.CUBIC_METERS if self.coordinator.data.volume_unit == IquaSoftenerVolumeUnit.LITERS else UnitOfVolume.GALLONS

class IquaSoftenerWaterUsageDailyAverageSensor(IquaSoftenerSensor):
    @property
    def native_value(self):
        value = self.coordinator.data.average_daily_use
        return value / 1000 if self.coordinator.data.volume_unit == IquaSoftenerVolumeUnit.LITERS else value

    @property
    def native_unit_of_measurement(self):
        return UnitOfVolume.CUBIC_METERS if self.coordinator.data.volume_unit == IquaSoftenerVolumeUnit.LITERS else UnitOfVolume.GALLONS
