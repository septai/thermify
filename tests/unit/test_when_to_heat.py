from __future__ import annotations

from datetime import UTC, datetime, timedelta

from config.settings import OptimizerSettings
from domain.when_to_heat import WhenToHeatPlanner


def _settings() -> OptimizerSettings:
    return OptimizerSettings(
        thermia_username_parameter="/lambda/thermia/username",
        thermia_password_parameter="/lambda/thermia/secret",
        cozify_config_parameter="/lambda/cozify/config",
        s3_bucket="spot-electricity-prices-149796722280-eu-west-1-an",
        s3_price_key="latest-prices.json",
        s3_heating_history_key="heating-history.json",
        s3_legionella_boost_key="latest-legionella-boost-time.json",
        nominal_target_temperature=20.0,
        nominal_indoor_temperature=21.0,
        min_target_temperature=17.0,
        max_target_temperature=21.0,
        reference_price=5.0,
        low_temperature_protection_margin=2.0,
        price_gain=1.2,
        indoor_temperature_gain=1.5,
        low_temperature_boost=3.0,
        default_heating_curve=36,
        aws_region="eu-west-1",
        timezone="Europe/Helsinki",
        log_level="INFO",
        thermia_demo_mode=False,
        shutdown_outdoor_temperature_limit=-5.0,
        shutdown_supply_line_temperature_limit=27,
        summer_mode_average_temperature_threshold=15.0,
        summer_mode_minimum_temperature_threshold=10.0,
        idle_target_temperature=10,
        min_run=1,
        min_idle=2,
        happy_price_bias=0.0,
        legionella_disinfection_temperature=60,
    )


def _iso_z(dt: datetime) -> str:
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def test_plan_returns_boolean_for_current_time_slot() -> None:
    now = datetime.now(UTC)
    current_slot_start = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)

    prices = []
    history = []
    for offset in range(-1, 3):
        start = current_slot_start + timedelta(minutes=15 * offset)
        end = start + timedelta(minutes=15) - timedelta(milliseconds=1)
        prices.append(
            {
                "price": float(1 + offset),
                "startDate": _iso_z(start),
                "endDate": _iso_z(end),
            }
        )

    planner = WhenToHeatPlanner(_settings())

    result = planner.plan(
        now=now,
        outdoor_temperature=20.0,
        prices_data=prices,
        history_data=history,
    )

    assert isinstance(result, bool)


def test_plan_keeps_off_run_until_min_idle_is_satisfied() -> None:
    now = datetime.now(UTC)
    current_slot_start = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)

    prices = []
    history = []
    for offset in range(-1, 3):
        start = current_slot_start + timedelta(minutes=15 * offset)
        end = start + timedelta(minutes=15) - timedelta(milliseconds=1)
        prices.append(
            {
                "price": 1.0,
                "startDate": _iso_z(start),
                "endDate": _iso_z(end),
            }
        )

    history.append(
        {
            "is_heating": False,
            "startDate": _iso_z(current_slot_start - timedelta(minutes=15)),
            "endDate": _iso_z(current_slot_start - timedelta(milliseconds=1)),
        }
    )

    planner = WhenToHeatPlanner(_settings())

    result = planner.plan(
        now=now,
        outdoor_temperature=20.0,
        prices_data=prices,
        history_data=history,
    )

    assert result is False
