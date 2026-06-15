"""Thermia API adapter wrapper for application-level usage."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, cast

from application.errors import NoHeatPumpsError, ThermiaApiError, ThermiaAuthenticationError


class OperationMode(StrEnum):
    AUTO = "AUTO"
    COMPRESSOR = "COMPRESSOR"
    HOT_WATER = "HOT_WATER"
    AUXILIARY = "AUXILIARY"
    OFF = "OFF"


LOGGER = logging.getLogger()


class ThermiaClient:
    """Thin wrapper around python-thermia-online-api with controlled errors."""

    def __init__(
        self,
        username: str,
        password: str,
        thermia_factory: Any | None = None,
        demo_mode: bool = False,
    ) -> None:
        if thermia_factory is None:
            from ThermiaOnlineAPI import Thermia

            thermia_factory = Thermia

        self._thermia = thermia_factory(username, password)
        self._heat_pump = self._get_first_heat_pump()
        self._demo_mode = demo_mode

        if not getattr(self._thermia, "connected", False):
            raise ThermiaAuthenticationError("Failed to authenticate to Thermia Online API")

    def _get_first_heat_pump(self) -> Any:
        heat_pumps = getattr(self._thermia, "heat_pumps", [])
        if not heat_pumps:
            raise NoHeatPumpsError("No Thermia heat pumps found for this account")
        return heat_pumps[0]

    def update_data(self) -> None:
        try:
            time.sleep(30)  # Wait for heat pump settings to get applied before updating data
            self._heat_pump.update_data()
        except Exception as exc:
            raise ThermiaApiError("Failed to update heat pump data") from exc

    def get_operation_mode(self) -> OperationMode:
        try:
            return cast(OperationMode, self._heat_pump.operation_mode)
        except Exception as exc:  # noqa: BLE001 - library throws generic exceptions
            raise ThermiaApiError("Failed to read current operation mode") from exc

    def set_operation_mode(self, mode: OperationMode) -> None:
        if self._demo_mode:
            LOGGER.info("DEMO MODE: would set operation mode to '%s'", mode)
            return

        LOGGER.debug(f"Setting operation mode to {mode}")
        try:
            self._heat_pump.set_operation_mode(mode)
            # Call twice to ensure the order is applied, as per user reports.
            time.sleep(10)
            self._heat_pump.set_operation_mode(mode)
        except Exception as exc:  # noqa: BLE001 - library throws generic exceptions
            raise ThermiaApiError(f"Failed to set operation mode to '{mode}'") from exc

    def set_target_temperature(self, target_temperature: int) -> None:
        """Set target temperature."""
        if not isinstance(target_temperature, int):
            raise ThermiaApiError("Target temperature must be an integer")

        if self._demo_mode:
            LOGGER.info(
                "DEMO MODE: would set target temperature to %s°C",
                target_temperature,
            )
            return

        LOGGER.debug(f"Setting target temperature to {target_temperature}°C")
        try:
            self._heat_pump.set_temperature(target_temperature)
            # Call twice to ensure the order is applied, as per user reports.
            time.sleep(10)
            self._heat_pump.set_temperature(target_temperature)
        except Exception as exc:  # noqa: BLE001 - library throws generic exceptions
            raise ThermiaApiError(
                f"Failed to set target temperature to '{target_temperature}'"
            ) from exc

    def get_heating_curve(self) -> int:
        try:
            return cast(
                int,
                self._heat_pump.get_register_data_by_register_group_and_name(
                    "REG_GROUP_HEATING_CURVE", "REG_HEATING_HEAT_CURVE"
                )["value"],
            )
        except Exception as exc:  # noqa: BLE001 - library throws generic exceptions
            raise ThermiaApiError("Failed to read heating curve") from exc

    def set_heating_curve(self, target_curve: int) -> None:
        """Set heating curve"""
        if not isinstance(target_curve, int):
            raise ThermiaApiError("Target curve must be an integer")

        if self._demo_mode:
            LOGGER.info("DEMO MODE: would set heating curve to '%s'", target_curve)
            return

        LOGGER.debug(f"Setting heating curve to {target_curve}")
        try:
            self._heat_pump.set_register_data_by_register_group_and_name(
                "REG_GROUP_HEATING_CURVE", "REG_HEATING_HEAT_CURVE", target_curve
            )
            # Call twice to ensure the order is applied, as per user reports.
            time.sleep(10)
            self._heat_pump.set_register_data_by_register_group_and_name(
                "REG_GROUP_HEATING_CURVE", "REG_HEATING_HEAT_CURVE", target_curve
            )
        except Exception as exc:
            raise ThermiaApiError(f"Failed to set heating curve to '{target_curve}'") from exc

    def is_heating(self) -> bool:
        try:
            return "HEATING" in self._heat_pump.running_operational_statuses
        except Exception as exc:  # noqa: BLE001 - library throws generic exceptions
            raise ThermiaApiError("Failed to read running operational statuses") from exc

    def is_hot_water(self) -> bool:
        try:
            return "HOT WATER" in self._heat_pump.running_operational_statuses
        except Exception as exc:  # noqa: BLE001 - library throws generic exceptions
            raise ThermiaApiError("Failed to read running operational statuses") from exc

    def is_brine_pump(self) -> bool:
        try:
            return "BRINEPUMP" in self._heat_pump.running_operational_statuses
        except Exception as exc:  # noqa: BLE001 - library throws generic exceptions
            raise ThermiaApiError("Failed to read running operational statuses") from exc

    def get_supply_line_temperature(self) -> int:
        try:
            return cast(
                int,
                self._heat_pump.supply_line_temperature,
            )
        except Exception as exc:  # noqa: BLE001 - library throws generic exceptions
            raise ThermiaApiError("Failed to read supply line temperature") from exc

    def get_desired_indoor_temperature(self) -> int:
        try:
            return cast(int, self._heat_pump.heat_temperature)
        except Exception as exc:  # noqa: BLE001 - library throws generic exceptions
            raise ThermiaApiError("Failed to read desired indoor temperature") from exc

    def get_outdoor_temperature(self) -> int:
        try:
            return cast(int, self._heat_pump.outdoor_temperature)
        except Exception as exc:  # noqa: BLE001 - library throws generic exceptions
            raise ThermiaApiError("Failed to read outdoor temperature") from exc

    def get_integral(self) -> int:
        try:
            return cast(int, self._heat_pump.operational_status_integral)
        except Exception as exc:  # noqa: BLE001 - library throws generic exceptions
            raise ThermiaApiError("Failed to read operational status integral") from exc

    def get_running_operational_statuses(self) -> str:
        return self._heat_pump.running_operational_statuses

    def get_hot_water_temperature(self) -> int:
        try:
            return cast(
                int,
                self._heat_pump.get_register_data_by_register_group_and_name(
                    "REG_GROUP_TEMPERATURES", "REG_HOT_WATER_TEMPERATURE"
                )["value"],
            )
        except Exception as exc:  # noqa: BLE001 - library throws generic exceptions
            raise ThermiaApiError("Failed to read hot water temperature") from exc

    def get_24h_historical_outdoor_temperatures(self) -> list[int]:
        try:
            outdoor_history = self._heat_pump.get_historical_data_for_register(
            "REG_OUTDOOR_TEMPERATURE",
            datetime.now() - timedelta(days=1),
            datetime.now(),
            )
            values = [item["value"] for item in outdoor_history]
            return values
        except Exception as exc:  # noqa: BLE001 - library throws generic exceptions
            raise ThermiaApiError("Failed to read historical outdoor temperatures") from exc
