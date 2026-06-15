#!/usr/bin/env python3
"""
Heating optimization using Integer Linear Programming (ILP).
Uses the PuLP library, quarter-hour electricity prices, and heating history
to calculate an optimal heating schedule.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime
from typing import TypedDict
from zoneinfo import ZoneInfo

import pulp

from config.settings import OptimizerSettings
from domain.types import HeatingHistoryEntry, PriceEntry

LOGGER = logging.getLogger()


class TimeseriesEntry(TypedDict):
    price: float
    startDate: str
    endDate: str
    is_heating: bool


class WhenToHeatPlanner:
    """Optimizes a quarter-hour heating schedule with MILP."""

    def __init__(self, settings: OptimizerSettings) -> None:
        self._settings = settings

    def log_plan(
        self,
        max_gap: int,
        min_run: int,
        min_idle: int,
        happy_price: float,
        heating_slots: int,
        timeseries: list[TimeseriesEntry],
        now_index: int,
    ) -> None:
        """Log max_gap, min_run, min_idle, happy_price and a visual schedule.

        The visual schedule shows up to `max_gap` past slots (most recent) and all future slots.
        Each hour is shown as: <symbols> where symbols are quarter-hour slots using
        🔥 for ON and ❄️ for OFF. The '|' marker is inserted at the beginning of the
        current slot (now_index).
        """
        # Determine included range: Show up to 12 hours of history (48 slots) and all future slots
        start = max(0, now_index - 48)
        end = len(timeseries)

        # Prepare timezone from settings.
        tz = ZoneInfo(self._settings.timezone)

        # Group slots per local day-hour (YYYY-MM-DD HH) so each hour has at most 4 positions
        hour_groups: dict[str, list[str | None]] = {}
        hour_order: list[str] = []
        for i in range(start, end):
            ts = timeseries[i]
            dt_str = ts["startDate"].replace("Z", "+00:00")
            slot_dt = datetime.fromisoformat(dt_str)
            local_dt = slot_dt.astimezone(tz)

            # Key by local date+hour to avoid mixing same-hour numbers from different days
            hour_key = local_dt.strftime("%Y-%m-%d %H")
            quarter_index = local_dt.minute // 15  # 0..3

            if hour_key not in hour_groups:
                hour_groups[hour_key] = [None, None, None, None]
                hour_order.append(hour_key)

            symbol = "🔥" if timeseries[i]["is_heating"] else "❄️"
            # Insert '|' marker for current slot at its position
            if i == now_index:
                symbol = "|" + symbol

            # Place symbol in the correct quarter position (overwrite if present)
            hour_groups[hour_key][quarter_index] = symbol

        # After filling, replace any None with ? so every hour has exactly 4 symbols
        parts: list[str] = []
        for hour_key in hour_order:
            local_hour = int(hour_key.split()[1])
            slots = [s if s is not None else "?" for s in hour_groups[hour_key]]
            symbols = "".join(slots)
            parts.append(f"{local_hour}{symbols}")
        visual = " ".join(parts)

        LOGGER.info(
            "max_gap=%d min_run=%d min_idle=%d happy_price=%.2f heating_slots=%d\nschedule=%s",
            max_gap,
            min_run,
            min_idle,
            happy_price,
            heating_slots,
            visual,
        )

    @staticmethod
    def _build_timeseries(
        prices: list[PriceEntry],
        history: list[HeatingHistoryEntry],
    ) -> list[TimeseriesEntry]:
        """
        Combine prices and history into a timeseries dictionary.
        If heating data is missing, the default value False is used.

        Returns a list where each item contains:
        {price, startDate, endDate, is_heating}
        """
        history_dict: dict[str, bool] = {}
        for entry in history:
            history_dict[entry["startDate"]] = entry["is_heating"]

        timeseries: list[TimeseriesEntry] = []
        for price_entry in prices:
            start_date = price_entry["startDate"]
            is_heating = history_dict.get(start_date, False)

            timeseries.append(
                {
                    "price": price_entry["price"],
                    "startDate": start_date,
                    "endDate": price_entry["endDate"],
                    "is_heating": is_heating,
                }
            )

        return timeseries

    @classmethod
    def _find_now_index(cls, now: datetime, timeseries: list[TimeseriesEntry]) -> int:
        """
        Find the current moment among the price entries.
        Returns the index of that entry.
        """
        now_str = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")

        index = next(
            (
                i
                for i, slot in enumerate(timeseries)
                if slot["startDate"] <= now_str <= slot["endDate"]
            ),
            None,
        )

        if index is None:
            raise ValueError("Current time not found in price data")

        if len(timeseries) < index:
            raise ValueError("Too few entries in price data")

        return index

    @staticmethod
    def _find_history_overlap(
        timeseries: list[TimeseriesEntry],
        history: list[HeatingHistoryEntry],
    ) -> list[bool | None]:
        """
        Find the part of the history that overlaps with the price data.
        Returns a list from history that matches the timeseries indices.
        """
        history_by_start: dict[str, bool]
        history_by_start = {entry["startDate"]: entry["is_heating"] for entry in history}

        history_overlap: list[bool | None]
        history_overlap = [
            history_by_start.get(ts_entry["startDate"], None) for ts_entry in timeseries
        ]
        return history_overlap

    @staticmethod
    def _calculate_heating_duty_cycle(outdoor_temperature: float) -> float:
        """
        Calculate the fraction of period in which heating needs to be active.
        The heuristic formula is derived from a linear regression.
        The parameters are tuned so that at 0°C, the system needs to run 10.19 hours per day,
        and at 12°C it doesn't need to run at all. The result is capped between 0 and 1,
        representing the fraction of time in which heating is needed.

        Your system may need more or less heating, so feel free to adjust the parameters as needed.
        """

        coefficient = -0.898
        intercept = 10.19
        h = coefficient * outdoor_temperature + intercept  # heating hours per 24 h.
        if h > 24:
            h = 24
        if h < 0:
            h = 0
        heating_duty_cycle = h / 24  # heating duty cycle is some number between [0, 1]
        return heating_duty_cycle

    @staticmethod
    def _calculate_happy_price(prices: list[float], reference_price: float) -> float:
        """Calculate the cutoff for a cheap price."""
        mean_price = sum(prices) / len(prices)
        variance = sum((p - mean_price) ** 2 for p in prices) / len(prices)
        std_dev = math.sqrt(variance)
        happy_price = min(reference_price, mean_price + std_dev)
        return happy_price

    @staticmethod
    def _calculate_max_gap(outdoor_temperature: float) -> int:
        """Calculate the longest continuous period heating may stay off.

        Magic number: 384 quarter-hours = 96 hours = 4 days,
        is returned when outdoor temperature is 15°C or higher,
        meaning there is effectively no gap constraint when it's warm.
        """
        if outdoor_temperature >= 15:
            max_gap = 384
        else:
            # Decreases as it gets colder, approaching 24 quarter-hours at 0°C
            max_gap = math.floor(384 / (16 - outdoor_temperature))
        return max_gap

    @staticmethod
    def _count_consecutive_off_before_now(
        history_overlap: list[bool | None],
        now_index: int,
    ) -> int:
        """
        How long has heating been "off" or unknown before now?
        Counts the number of consecutive "off" or unknown slots in the history before the
        current time.
        """
        count = 0
        for i in range(now_index - 1, -1, -1):
            if history_overlap[i] is False or history_overlap[i] is None:
                count += 1
            else:
                break
        return count

    @staticmethod
    def _count_consecutive_on_before_now(
        history_overlap: list[bool | None],
        now_index: int,
    ) -> int:
        """
        How long has heating been "on" before now?
        Counts the number of consecutive "on" slots in the history before the current time.
        """
        count = 0
        for i in range(now_index - 1, -1, -1):
            if history_overlap[i] is True:
                count += 1
            else:
                break
        return count

    def plan(
        self,
        now: datetime,
        outdoor_temperature: float,
        prices_data: list[PriceEntry],
        history_data: list[HeatingHistoryEntry],
    ) -> bool:
        """
        Optimize the heating schedule using Integer Linear Programming.
        Happy_price_bias = 2.0 (roughly) would use all happy-price quarter-hours for heating.
        """
        happy_price_bias = self._settings.happy_price_bias
        min_run = self._settings.min_run
        min_idle = self._settings.min_idle

        # Build timeseries
        timeseries = self._build_timeseries(prices_data, history_data)

        # Find the index of now in timeseries
        now_index = self._find_now_index(now, timeseries)

        # Calculate parameters
        prices = [ts["price"] for ts in timeseries]
        happy_price = self._calculate_happy_price(prices, self._settings.reference_price)
        max_gap = self._calculate_max_gap(outdoor_temperature)
        num_future_slots = len(timeseries) - now_index
        heating_per_slot = self._calculate_heating_duty_cycle(outdoor_temperature)
        heating_slots = math.ceil(heating_per_slot * num_future_slots)

        # if heating_slots == 0:
        #   # No heating needed, return False immediately
        #   LOGGER.info("No heating needed based on outdoor temperature: %d°C", outdoor_temperature)
        #   return False

        # Find the overlapping portion in the history
        history_overlap = self._find_history_overlap(timeseries, history_data)

        # Count consecutive "off" and "on" states at the end of the history
        consecutive_off_before = self._count_consecutive_off_before_now(history_overlap, now_index)
        consecutive_on_before = self._count_consecutive_on_before_now(history_overlap, now_index)

        # ILP model
        problem: pulp.LpProblem = pulp.LpProblem("Heating_Optimization", pulp.LpMinimize)

        # Variables: schedule[i] = 1 if quarter-hour i is heated, 0 otherwise (ILP binary)
        # Only optimize the future (i >= now_index)

        schedule: list[pulp.LpVariable] = [
            pulp.LpVariable(f"schedule_{i}", cat="Binary") for i in range(num_future_slots)
        ]

        # Objective: minimize cost, but prioritize happy quarter-hours
        # Add a soft bonus for cheap quarter-hours (price <= happy_price)
        cost = pulp.lpSum([prices[now_index + i] * schedule[i] for i in range(num_future_slots)])
        happy_bonus = pulp.lpSum(
            [schedule[i] for i in range(num_future_slots) if prices[now_index + i] <= happy_price]
        )

        objective = cost - happy_price_bias * happy_bonus  # Give the bonus significant weight
        problem += objective

        # Constraint 1: Minimum number of heating intervals

        problem += pulp.lpSum(schedule) >= heating_slots

        # Constraint 2: Gap constraint (max_gap consecutive off)
        # There may not be more than max_gap consecutive OFF slots
        for i in range(num_future_slots - max_gap):
            # Check all windows of length max_gap+1
            gap_sum = pulp.lpSum([schedule[i + j] for j in range(max_gap + 1)])
            problem += gap_sum >= 1

        # Gap constraint accounting for history
        if consecutive_off_before > 0:
            remaining_off_allowed = max_gap - consecutive_off_before

            if remaining_off_allowed < 0:
                # The end of the history already has >= max_gap unheated intervals,
                # so heating must start immediately
                problem += schedule[0] == 1
            elif remaining_off_allowed < num_future_slots:
                # At least one schedule[0..remaining_off_allowed] must be 1
                problem += pulp.lpSum(schedule[: remaining_off_allowed + 1]) >= 1

        # Constraint 3: Run constraint (min_run consecutive 'on' heating slots)
        # Each on-run must have length >= min_run

        # Binary helper variable run_end =
        #   1 -> run ends at the boundary between slot i and i+1: [1 0]
        #   0 -> otherwise: [0 0], [0 1], [1 1]
        # Either (schedule[i] = 1 and schedule[i+1] = 0) or (i is the last slot and schedule[i] = 1)
        run_end: list[pulp.LpVariable] = [
            pulp.LpVariable(f"run_end_{i}", cat="Binary") for i in range(num_future_slots)
        ]

        # This constraint set makes run_end[i] equal to 1 exactly when a running schedule
        # switches from ON at i to OFF at i+1, i.e., it marks the end of a run.
        # MILP-solvers cannot use if statements, so logic is encoded with
        # binary variables and linear constraints.
        # Effectively, run_end[i] = schedule[i] * (1 - schedule[i+1])
        for i in range(num_future_slots - 1):
            # If a run ends at time i, then the system must be running at time i.
            # run_end[i] <= schedule[i]
            problem += run_end[i] <= schedule[i]
            # If a run ends at time i, then the next slot must be off.
            # run_end[i] <= 1 - schedule[i+1]
            problem += run_end[i] <= 1 - schedule[i + 1]
            # Forces run_end[i] = 1 when a run transitions from ON to OFF
            # run_end[i] >= schedule[i] - schedule[i+1]
            problem += run_end[i] >= schedule[i] - schedule[i + 1]
        # Last slot (i = num_future_slots - 1)
        # If the system is running in the final slot, that run must be counted as ending there.
        if num_future_slots > 0:
            problem += run_end[num_future_slots - 1] >= schedule[num_future_slots - 1]

        # If a run ends at index i, the last min_run quarter-hours must be ON
        # (This implicitly assumes the system was OFF before time 0.)
        for i in range(num_future_slots):
            run_length = pulp.lpSum(
                [
                    schedule[max(0, i - min_run + 1 + j)] for j in range(min_run)
                ]  # Counts the last min_run slots; early windows repeat clipped values.
            )
            # run_length >= min_run * run_end[i]
            problem += run_length >= min_run * run_end[i]

        # Run constraint accounting for history
        # If the system was already ON before the planning horizon started,
        # we must finish that run correctly.
        if consecutive_on_before > 0 and consecutive_on_before < min_run:
            remaining_needed = min_run - consecutive_on_before
            # schedule[0] and the following remaining_needed-1 intervals must be 1
            problem += schedule[0] == 1
            for j in range(1, min(remaining_needed, num_future_slots)):
                problem += schedule[j] == 1  # Equality (== 1) enforces this condition

        # Constraint 4: Idle constraint (min_idle consecutive 'off' heating slots)
        # Each off-run must have length >= min_idle
        idle_end: list[pulp.LpVariable] = [
            pulp.LpVariable(f"idle_end_{i}", cat="Binary") for i in range(num_future_slots)
        ]

        # idle_end[i] marks the end of an OFF run:
        #   1 -> schedule[i] is OFF and the next slot is ON (or this is the last slot)
        #   0 -> otherwise
        for i in range(num_future_slots - 1):
            problem += idle_end[i] <= 1 - schedule[i]
            problem += idle_end[i] <= schedule[i + 1]
            problem += idle_end[i] >= schedule[i + 1] - schedule[i]
        if num_future_slots > 0:
            problem += idle_end[num_future_slots - 1] >= 1 - schedule[num_future_slots - 1]

        for i in range(num_future_slots):
            idle_length = pulp.lpSum(
                [1 - schedule[max(0, i - min_idle + 1 + j)] for j in range(min_idle)]
            )
            problem += idle_length >= min_idle * idle_end[i]

        if consecutive_off_before > 0 and consecutive_off_before < min_idle:
            remaining_needed = min_idle - consecutive_off_before
            problem += schedule[0] == 0
            for j in range(1, min(remaining_needed, num_future_slots)):
                problem += schedule[j] == 0

        # Solve
        statusCode = problem.solve(pulp.PULP_CBC_CMD(msg=False))
        statusInfo = pulp.LpStatus[statusCode]

        # Extract the schedule and update the timeseries with the planned heating
        has_none = any(s.varValue is None for s in schedule[:num_future_slots])
        for i in range(num_future_slots):
            idx = now_index + i
            if has_none:
                timeseries[idx]["is_heating"] = True
            else:
                timeseries[idx]["is_heating"] = schedule[i].varValue >= 0.5  # type: ignore

        self.log_plan(max_gap, min_run, min_idle, happy_price, heating_slots, timeseries, now_index)

        if statusInfo != "Optimal" or schedule[0].varValue is None:
            LOGGER.warning("Solver status: %s", statusInfo)
            return True  # Default to heating if no optimal solution is found

        return schedule[0].varValue >= 0.5
