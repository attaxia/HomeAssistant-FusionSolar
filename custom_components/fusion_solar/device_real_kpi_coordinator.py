from datetime import timedelta
import math
import logging

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .fusion_solar.const import ATTR_DEVICE_REAL_KPI_DEV_ID, ATTR_DEVICE_REAL_KPI_DATA_ITEM_MAP, \
    PARAM_DEVICE_TYPE_ID_STRING_INVERTER, PARAM_DEVICE_TYPE_ID_EMI, PARAM_DEVICE_TYPE_ID_GRID_METER, \
    PARAM_DEVICE_TYPE_ID_RESIDENTIAL_INVERTER, PARAM_DEVICE_TYPE_ID_BATTERY, PARAM_DEVICE_TYPE_ID_POWER_SENSOR
from .fusion_solar.openapi.openapi_api import FusionSolarOpenApiAccessFrequencyTooHighError

_LOGGER = logging.getLogger(__name__)


class DeviceRealKpiDataCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, api, devices):
        self.name = 'FusionSolarOpenAPIDeviceRealKpiType'

        super().__init__(
            hass,
            _LOGGER,
            name=self.name,
            update_interval=timedelta(minutes=1),
        )

        self.api = api
        self.devices = devices
        self.skip_counter = 0
        self.skip = False
        self.counter = 0

    async def _async_update_data(self):
        if self.should_skip:
            self.skip_counter += 1
            _LOGGER.warning(
                f'{self.name} Skipped call due to rate limiting. Wait for {self.skip_for} seconds. {self.skip_counter}/{self.counter_limit}')
            raise UpdateFailed(f'Skipped call due to rate limiting. Wait for {self.skip_for} seconds.')

        data = {}
        device_ids_grouped_per_type_id = self.device_ids_grouped_per_type_id()
        index_to_fetch = self.counter % len(device_ids_grouped_per_type_id)
        type_id_to_fetch = list(device_ids_grouped_per_type_id.keys())[index_to_fetch]

        self.counter += 1

        try:
            response = await self.hass.async_add_executor_job(
                self.api.get_dev_real_kpi,
                device_ids_grouped_per_type_id[type_id_to_fetch],
                type_id_to_fetch
            )
            self.skip = False
            self.skip_counter = 0
        except FusionSolarOpenApiAccessFrequencyTooHighError as e:
            self.skip = True
            raise UpdateFailed(f'Error fetching data: {e}') from e

        for response_data in response:
            key = f'{DOMAIN}-{response_data[ATTR_DEVICE_REAL_KPI_DEV_ID]}'
            data[key] = response_data[ATTR_DEVICE_REAL_KPI_DATA_ITEM_MAP]

        _LOGGER.debug(f'async_update_device_real_kpi_data: {data}')

        return data

    def device_ids_grouped_per_type_id(self):
        device_ids_grouped_per_type_id = {}

        for device in self.devices:
            # skip devices wherefore no real kpi data is available
            if device.type_id not in [PARAM_DEVICE_TYPE_ID_STRING_INVERTER, PARAM_DEVICE_TYPE_ID_EMI,
                                      PARAM_DEVICE_TYPE_ID_GRID_METER, PARAM_DEVICE_TYPE_ID_RESIDENTIAL_INVERTER,
                                      PARAM_DEVICE_TYPE_ID_BATTERY, PARAM_DEVICE_TYPE_ID_POWER_SENSOR]:
                continue

            if device.type_id not in device_ids_grouped_per_type_id:
                device_ids_grouped_per_type_id[device.type_id] = []
            device_ids_grouped_per_type_id[device.type_id].append(str(device.device_id))

        return device_ids_grouped_per_type_id

    @property
    def counter_limit(self) -> int:
        return math.ceil(60 / self.update_interval.total_seconds()) + 1

    @property
    def should_skip(self) -> bool:
        return self.skip and self.skip_counter <= self.counter_limit

    @property
    def skip_for(self) -> int:
        return (self.counter_limit - self.skip_counter + 1) * self.update_interval.total_seconds()
