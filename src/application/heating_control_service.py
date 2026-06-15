"""Application service for price-driven Thermia target temperature control."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from adapters.thermia_client import OperationMode
from application.errors import (
    CozifyAuthenticationError,
    CozifyDataError,
    S3DataRetrievalError,
    S3DataValidationError,
    ThermiaApiError,
)
from config.settings import OptimizerSettings
from domain.datetime_utils import _parse_iso8601_utc, _parse_utc_iso8601
from domain.how_much_to_heat import TemperatureControlConstants, compute_target_temperature
from domain.interfaces import CozifyClientProtocol, S3ClientProtocol, ThermiaClientProtocol
from domain.types import HeatingHistoryEntry, PriceEntry
from domain.when_to_heat import WhenToHeatPlanner

LOGGER = logging.getLogger()


class FallbackReason(StrEnum):
    COZIFY_UNAVAILABLE = "cozify_unavailable"
    PRICE_DATA_UNAVAILABLE = "price_data_unavailable"


@dataclass(frozen=True)
class HeatingControlResult:
    """Result payload returned from heating control operation."""

    is_summer: bool
    price: float | None
    indoor_temperature: float | None
    outdoor_temperature: float | None
    target_temperature: float
    fallback_used: bool
    fallback_reason: str | None


class HeatingControlService:
    """Orchestrates reads from S3 and Cozify,
    calculates target temperature, then applies it on Thermia."""

    def __init__(
        self,
        settings: OptimizerSettings,
        s3_client: S3ClientProtocol,
        thermia_client: ThermiaClientProtocol,
        cozify_client: CozifyClientProtocol,
    ) -> None:
        self._settings = settings
        self._s3_client = s3_client
        self._thermia_client = thermia_client
        self._cozify_client = cozify_client

    def _current_slot_bounds(self, now: datetime) -> tuple[datetime, datetime]:
        """Calculate the start and end timestamps for the current 15-minute slot."""
        slot_start = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
        slot_end = slot_start + timedelta(minutes=15) - timedelta(milliseconds=1)
        return slot_start, slot_end

    def _get_current_price(self, prices: list[PriceEntry], now: datetime) -> float:
        """Extract current price from S3 price data payload."""
        for slot in prices:
            start = _parse_iso8601_utc(slot["startDate"])
            end = _parse_iso8601_utc(slot["endDate"])

            if start <= now <= end:
                return float(slot["price"])
        raise S3DataValidationError("No current quarter-hour price slot found in S3 payload")

    def _read_price_data(self, now: datetime) -> list[PriceEntry] | None:
        """Read and return spot prices data and extracted current price from S3"""
        try:
            payload = self._s3_client.read_json(
                bucket=self._settings.s3_bucket,
                key=self._settings.s3_price_key,
            )
            prices = payload.get("prices")
        except (S3DataRetrievalError, S3DataValidationError, TypeError):
            return None
        return prices

    def _get_prices_for_upcoming_hour(self, prices: list[PriceEntry], now: datetime) -> list[float]:
        """Extract spot prices for the next hour from S3 price data payload."""
        upcoming_prices = []
        for slot in prices:
            end = _parse_iso8601_utc(slot["endDate"])
            if now <= end <= now + timedelta(hours=1):
                upcoming_prices.append(slot["price"])
        if len(upcoming_prices) < 4:
            upcoming_prices.extend([float("inf")] * (4 - len(upcoming_prices)))
        return upcoming_prices

    def _read_heating_history(self) -> list[HeatingHistoryEntry]:
        """Read and return heating history data from S3, or return empty list if retrieval fails."""
        try:
            payload = self._s3_client.read_json(
                bucket=self._settings.s3_bucket,
                key=self._settings.s3_heating_history_key,
            )
            history = payload.get("history", [])
        except (S3DataRetrievalError, S3DataValidationError):
            return []
        return history

    def _calculate_target_temperature_with_fallback(
        self,
        price: float | None,
        indoor_temperature: float | None,
    ) -> tuple[str | None, float]:
        """Calculate target temperature based on price and indoor temperature,
        with fallback to nominal target if data is unavailable."""

        if price is None:
            return FallbackReason.PRICE_DATA_UNAVAILABLE, self._settings.nominal_target_temperature

        if indoor_temperature is None:
            return FallbackReason.COZIFY_UNAVAILABLE, self._settings.nominal_target_temperature

        constants = TemperatureControlConstants(
            nominal_target_temperature=self._settings.nominal_target_temperature,
            nominal_indoor_temperature=self._settings.nominal_indoor_temperature,
            min_target_temperature=self._settings.min_target_temperature,
            max_target_temperature=self._settings.max_target_temperature,
            reference_price=self._settings.reference_price,
            low_temperature_protection_margin=self._settings.low_temperature_protection_margin,
            price_gain=self._settings.price_gain,
            indoor_temperature_gain=self._settings.indoor_temperature_gain,
            low_temperature_boost=self._settings.low_temperature_boost,
        )
        return None, compute_target_temperature(
            price=price,
            indoor_temperature=indoor_temperature,
            constants=constants,
        )

    def _should_heat_now(
        self,
        now: datetime,
        outdoor_temperature: float | None,
        indoor_temperature: float | None,
        prices: list[PriceEntry] | None,
        history: list[HeatingHistoryEntry],
    ) -> bool:
        """Determine whether the heat pump should be active in the current slot based on inputs."""

        if indoor_temperature is None or outdoor_temperature is None or prices is None:
            return True

        try:
            result = WhenToHeatPlanner(self._settings).plan(
                now=now,
                outdoor_temperature=outdoor_temperature,
                prices_data=prices,
                history_data=history,
            )
            return result
        except ValueError as exc:
            LOGGER.exception("Failed to compute heating schedule: %s", exc)
            return True

    def _validate_mode_switch(
        self,
        new_mode: OperationMode,
        indoor_temperature: float | None,
        outdoor_temperature: float | None,
    ) -> bool:
        """Check if it's currently allowed to change the heat pump's operation mode"""

        current_mode = self._thermia_client.get_operation_mode()

        # Always allow switching to AUTO.
        if new_mode == OperationMode.AUTO:
            return True

        # If the heat pump is OFF, allow switching to any other mode
        if current_mode == OperationMode.OFF:
            return True

        (
            is_indoor_temperature_safe,
            is_outdoor_temperature_safe,
            is_supply_line_temperature_safe,
        ) = self._assess_mode_switch_temperatures(indoor_temperature, outdoor_temperature)
        running_statuses = self._thermia_client.get_running_operational_statuses()
        is_not_running = all(
            status not in running_statuses for status in ["HEATING", "HOT_WATER", "BRINEPUMP"]
        )

        match current_mode, new_mode:
            case OperationMode.AUTO, OperationMode.AUTO:
                return True

            case OperationMode.COMPRESSOR, OperationMode.COMPRESSOR:
                return True

            case OperationMode.HOT_WATER, OperationMode.HOT_WATER:
                return is_indoor_temperature_safe and is_outdoor_temperature_safe

            case OperationMode.OFF, OperationMode.OFF:
                return is_indoor_temperature_safe and is_outdoor_temperature_safe

            case OperationMode.AUTO, OperationMode.COMPRESSOR:
                # Only switch from AUTO to COMPRESSOR if hot water is not being made.
                # This avoids stopping a possible legionella boost.
                return "HOT_WATER" not in running_statuses

            case OperationMode.AUTO | OperationMode.COMPRESSOR, OperationMode.HOT_WATER:
                return (
                    is_indoor_temperature_safe
                    and is_outdoor_temperature_safe
                    and is_supply_line_temperature_safe
                    and "HEATING" not in running_statuses
                )

            case OperationMode.AUTO | OperationMode.COMPRESSOR, OperationMode.OFF:
                return (
                    is_indoor_temperature_safe
                    and is_outdoor_temperature_safe
                    and is_supply_line_temperature_safe
                    and is_not_running
                )

            case OperationMode.HOT_WATER, OperationMode.COMPRESSOR:
                return True

            case OperationMode.HOT_WATER, OperationMode.OFF:
                return is_not_running

        return True

    def _assess_mode_switch_temperatures(
        self,
        indoor_temperature: float | None,
        outdoor_temperature: float | None,
    ) -> tuple[bool, bool, bool]:
        """Evaluate and return the conditions relevant for switching operation modes."""

        if indoor_temperature is None:
            is_indoor_temperature_safe = False
        else:
            is_indoor_temperature_safe = indoor_temperature > (
                self._settings.nominal_indoor_temperature
                - self._settings.low_temperature_protection_margin
            )

        if outdoor_temperature is None:
            is_outdoor_temperature_safe = False
        else:
            is_outdoor_temperature_safe = (
                outdoor_temperature > self._settings.shutdown_outdoor_temperature_limit
            )

        is_supply_line_temperature_safe = (
            self._thermia_client.get_supply_line_temperature()
            < self._settings.shutdown_supply_line_temperature_limit
        )

        return (
            is_indoor_temperature_safe,
            is_outdoor_temperature_safe,
            is_supply_line_temperature_safe,
        )

    def _apply_active_heating(
        self,
        target_temperature: float,
        now: datetime,
        prices: list[PriceEntry] | None,
    ) -> None:
        """Apply heating control by setting target temperature, adjusting heating curve,
        and potentially enabling legionella boost mode."""

        setpoint_temperature, curve_offset = self._to_thirds(target_temperature)
        adjusted_curve = self._settings.default_heating_curve + curve_offset
        self._thermia_client.set_target_temperature(setpoint_temperature)
        self._thermia_client.set_heating_curve(adjusted_curve)
        operation_mode = (
            OperationMode.AUTO
            if self._is_legionella_boost_needed(now, prices)
            else OperationMode.COMPRESSOR
        )
        if self._validate_mode_switch(operation_mode, None, None):
            self._thermia_client.set_operation_mode(operation_mode)

    def _apply_idle_heating(
        self,
        indoor_temperature: float | None,
        outdoor_temperature: float | None,
        now: datetime,
        prices: list[PriceEntry] | None,
    ) -> None:
        """Apply idle heating control."""

        operation_mode = self._select_idle_operation_mode(
            now,
            prices,
            indoor_temperature,
            outdoor_temperature,
        )

        if operation_mode is None:
            return

        self._apply_idle_operation_mode(operation_mode)

    def _apply_idle_operation_mode(self, operation_mode: OperationMode) -> None:
        if operation_mode in {OperationMode.AUTO, OperationMode.COMPRESSOR}:
            self._thermia_client.set_target_temperature(self._settings.idle_target_temperature)
            self._thermia_client.set_heating_curve(self._settings.default_heating_curve)

        self._thermia_client.set_operation_mode(operation_mode)

    def _select_idle_operation_mode(
        self,
        now,
        prices,
        indoor_temperature: float | None,
        outdoor_temperature: float | None,
    ) -> OperationMode | None:
        candidates = [
            # (
            #     OperationMode.AUTO,
            #     lambda: self._is_legionella_boost_needed(now, prices)
            #     and self._validate_mode_switch(
            #         OperationMode.AUTO,
            #         indoor_temperature,
            #         outdoor_temperature
            #     ),
            #     "Legionella boost needed, switching to AUTO mode",
            # ),
            (
                OperationMode.HOT_WATER,
                lambda: self._validate_mode_switch(
                    OperationMode.HOT_WATER,
                    indoor_temperature,
                    outdoor_temperature,
                ),
                "Safe to switch to HOT_WATER mode",
            ),
            (
                OperationMode.AUTO
                if self._is_legionella_boost_needed(now, prices)
                else OperationMode.COMPRESSOR,
                # OperationMode.COMPRESSOR,
                lambda: self._validate_mode_switch(
                    OperationMode.AUTO
                    if self._is_legionella_boost_needed(now, prices)
                    else OperationMode.COMPRESSOR,
                    # OperationMode.COMPRESSOR,
                    indoor_temperature,
                    outdoor_temperature,
                ),
                "Applying idle heating with COMPRESSOR/AUTO mode",
            ),
        ]

        for mode, condition, log_message in candidates:
            if condition():
                LOGGER.info(log_message)
                return mode

        return None

    def _apply_heating_control(
        self,
        is_summer: bool,
        is_heating_slot: bool,
        target_temperature: float,
        now: datetime,
        prices: list[PriceEntry] | None,
        indoor_temperature: float | None,
        outdoor_temperature: float | None,
    ) -> bool:
        """Apply active heating if it's not summer and the current slot is a heating slot;
        otherwise, use idle heating.

        Return True if the heat pump is actively heating after applying control, otherwise False."""

        if is_heating_slot and not is_summer:
            self._apply_active_heating(target_temperature, now, prices)
            return True

        self._apply_idle_heating(indoor_temperature, outdoor_temperature, now, prices)
        return False

    def _is_summer(self) -> bool:
        """Determine if it's currently summer based on historical outdoor temperature data."""

        try:
            outdoor_temperatures = self._thermia_client.get_24h_historical_outdoor_temperatures()
        except ThermiaApiError as exc:
            LOGGER.exception("Thermia API Error: %s", exc)
            return False

        average_outdoor_temperature = sum(outdoor_temperatures) / len(outdoor_temperatures)
        min_outdoor_temperature = min(outdoor_temperatures)
        LOGGER.info(
            "Average outdoor temperature over the last 24h: %.2f°C", average_outdoor_temperature
        )
        LOGGER.info(
            "Minimum outdoor temperature over the last 24h: %.2f°C", min_outdoor_temperature
        )

        is_summer = (
            average_outdoor_temperature >= self._settings.summer_mode_average_temperature_threshold
            and min_outdoor_temperature >= self._settings.summer_mode_minimum_temperature_threshold
        )
        LOGGER.info("Determined is_summer=%s based on configured thresholds", is_summer)
        return is_summer

    def _replace_or_append_history_entry(
        self,
        history: list[HeatingHistoryEntry],
        new_history_entry: HeatingHistoryEntry,
    ) -> list[HeatingHistoryEntry]:
        """Update the heating history entries with a new entry for the current slot."""

        updated_history = history.copy()
        for idx, entry in enumerate(updated_history):
            if (
                entry.get("startDate") == new_history_entry["startDate"]
                and entry.get("endDate") == new_history_entry["endDate"]
            ):
                updated_history[idx] = new_history_entry
                return updated_history

        updated_history.append(new_history_entry)
        return updated_history

    def _prune_history(
        self,
        history: list[HeatingHistoryEntry],
        threshold: datetime,
    ) -> list[HeatingHistoryEntry]:
        """Prune heating history entries that are older than the given threshold timestamp."""

        pruned_history: list[HeatingHistoryEntry] = []
        for entry in history:
            entry_start = _parse_iso8601_utc(entry["startDate"])

            if entry_start >= threshold:
                pruned_history.append(entry)

        return pruned_history

    def _persist_heating_history(
        self,
        history: list[HeatingHistoryEntry],
        slot_start: datetime,
        slot_end: datetime,
        is_heating_slot: bool,
    ) -> None:
        """Persist heating history back to S3"""

        new_history_entry: HeatingHistoryEntry = {
            "is_heating": is_heating_slot,
            "startDate": _parse_utc_iso8601(slot_start),
            "endDate": _parse_utc_iso8601(slot_end),
        }
        updated_history = self._replace_or_append_history_entry(history, new_history_entry)
        pruned_history = self._prune_history(updated_history, slot_start - timedelta(hours=12))

        try:
            self._s3_client.write_json(
                bucket=self._settings.s3_bucket,
                key=self._settings.s3_heating_history_key,
                payload={"history": pruned_history},
            )
        except (S3DataRetrievalError, S3DataValidationError) as exc:
            LOGGER.exception("Failed to update heating history in S3: %s", exc)

    def _persist_legionella_boost_time(self, now: datetime) -> None:
        """Persist the given legionella boost time to S3."""
        try:
            hot_water_temperature = self._thermia_client.get_hot_water_temperature()
        except ThermiaApiError as exc:
            LOGGER.exception("Failed to retrieve hot water temperature: %s", exc)
            return

        try:
            if hot_water_temperature > self._settings.legionella_disinfection_temperature:
                self._write_legionella_boost_time(now)
        except (S3DataRetrievalError, S3DataValidationError) as exc:
            LOGGER.exception("Failed to persist legionella boost time to S3: %s", exc)

    def _to_thirds(self, t: float) -> tuple[int, int]:
        """
        Maps a floating-point value to an integer reference and a 3-level sub-index

        Returns (n, k), where
        - n is an integer reference value computed as n = floor(t + 0.17)
        - k is an integer sub-index in {0, 1, 2} indicating which third around n contains t

        The interval (n - 0.17, n + 0.83] is divided into three contiguous sub-intervals:
        - k = 0 if t ∈ (n - 0.17, n + 0.17]
        - k = 1 if t ∈ (n + 0.17, n + 0.50]
        - k = 2 if t ∈ (n + 0.50, n + 0.83]
        """

        n = math.floor(t + 0.17)
        x = t - n + 0.17
        k = max(0, min(2, math.floor(x / 0.33)))

        return n, k

    def _is_legionella_boost_needed(self, now: datetime, prices: list[PriceEntry] | None) -> bool:
        """Determine if legionella boost is needed based on days since the last boost."""

        if prices is None:
            return False

        days_since_boost = self._days_since_last_legionella_boost(now)
        prices_for_upcoming_hour = self._get_prices_for_upcoming_hour(prices, now)
        is_price_affordable = max(prices_for_upcoming_hour) <= self._settings.reference_price

        match now.isoweekday():
            case 1:  # Monday
                return days_since_boost > 13 or (is_price_affordable and days_since_boost >= 8)
            case 2:  # Tuesday
                return days_since_boost > 13 or (is_price_affordable and days_since_boost >= 9)
            case 3:  # Wednesday
                return days_since_boost > 13 or (is_price_affordable and days_since_boost >= 10)
            case 4:  # Thursday
                return days_since_boost > 13 or (is_price_affordable and days_since_boost >= 11)
            case 5:  # Friday
                return days_since_boost > 13 or (is_price_affordable and days_since_boost >= 12)
            case 6:  # Saturday
                return days_since_boost > 10 or (is_price_affordable and days_since_boost >= 3)
            case 7:  # Sunday
                return days_since_boost > 9 or (is_price_affordable and days_since_boost >= 3)

        return False

    def _days_since_last_legionella_boost(self, now: datetime) -> int:
        """Return the number of days since the last legionella boost based on S3 data."""

        latest_boost_time = self._read_legionella_boost_time()
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_last_boost_day = latest_boost_time.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        days_since_last_boost = (start_of_today - start_of_last_boost_day).days
        return days_since_last_boost

    def _read_legionella_boost_time(self) -> datetime:
        """Read the last legionella boost time from S3 or recover with a default timestamp."""

        try:
            payload = self._s3_client.read_json(
                bucket=self._settings.s3_bucket,
                key=self._settings.s3_legionella_boost_key,
            )
            latest_boost_time = _parse_iso8601_utc(payload.get("latest_legionella_boost_time"))
            return latest_boost_time
        except (S3DataRetrievalError, S3DataValidationError) as exc:
            LOGGER.warning("Unable to read legionella boost time from S3: %s", exc)
            LOGGER.warning(
                "Writing default boost time (7 days ago) to S3 to recover from potential "
                "data issues."
            )
            default_boost_time = datetime.now(UTC) - timedelta(days=7)
            try:
                self._write_legionella_boost_time(default_boost_time)
            except (S3DataRetrievalError, S3DataValidationError) as write_exc:
                LOGGER.exception(
                    "Failed to write default legionella boost time to S3: %s",
                    write_exc,
                )
            return default_boost_time

    def _write_legionella_boost_time(self, boost_time: datetime) -> None:
        """Write the given legionella boost time to S3."""
        self._s3_client.write_json(
            bucket=self._settings.s3_bucket,
            key=self._settings.s3_legionella_boost_key,
            payload={"latest_legionella_boost_time": _parse_utc_iso8601(boost_time)},
        )

    def _read_indoor_temperature(self) -> float | None:
        if self._cozify_client is None:
            LOGGER.warning("Cozify client is not initialized")
            return None
        try:
            sensor_id = self._cozify_client.get_configured_temperature_sensor_id()
            return self._cozify_client.get_room_temperature(sensor_id)
        except (CozifyAuthenticationError, CozifyDataError) as exc:
            LOGGER.exception("Failed to read indoor temperature from Cozify: %s", exc)
            return None

    def _read_outdoor_temperature(self) -> float | None:
        try:
            return self._thermia_client.get_outdoor_temperature()
        except ThermiaApiError as exc:
            LOGGER.exception("Failed to read outdoor temperature from Thermia: %s", exc)
            return None

    def execute(self) -> HeatingControlResult:
        now = datetime.now(UTC)
        slot_start, slot_end = self._current_slot_bounds(now)

        prices = self._read_price_data(now)
        price = self._get_current_price(prices, now) if prices is not None else None
        indoor_temperature = self._read_indoor_temperature()
        outdoor_temperature = self._read_outdoor_temperature()
        is_summer = self._is_summer()
        fallback_reason, target_temperature = self._calculate_target_temperature_with_fallback(
            price=price,
            indoor_temperature=indoor_temperature,
        )
        history = self._read_heating_history()
        is_heating_slot = self._should_heat_now(
            now=now,
            outdoor_temperature=outdoor_temperature,
            indoor_temperature=indoor_temperature,
            prices=prices,
            history=history,
        )
        do_we_heat = self._apply_heating_control(
            is_summer=is_summer,
            is_heating_slot=is_heating_slot,
            target_temperature=target_temperature,
            now=now,
            prices=prices,
            indoor_temperature=indoor_temperature,
            outdoor_temperature=outdoor_temperature,
        )
        self._persist_heating_history(
            history=history,
            slot_start=slot_start,
            slot_end=slot_end,
            is_heating_slot=do_we_heat,
        )
        self._persist_legionella_boost_time(now)

        return HeatingControlResult(
            is_summer=is_summer,
            price=price,
            indoor_temperature=indoor_temperature,
            outdoor_temperature=outdoor_temperature,
            target_temperature=target_temperature,
            fallback_used=fallback_reason is not None,
            fallback_reason=fallback_reason,
        )
