from domain.how_much_to_heat import (
    TemperatureControlConstants,
    clamp,
    compute_target_temperature,
)


def _constants() -> TemperatureControlConstants:
    return TemperatureControlConstants(
        nominal_target_temperature=20.0,
        nominal_indoor_temperature=21.0,
        min_target_temperature=17.0,
        max_target_temperature=21.0,
        reference_price=5.0,
        low_temperature_protection_margin=2.0,
        price_gain=1.2,
        indoor_temperature_gain=1.5,
        low_temperature_boost=3.0,
    )


def test_clamp_limits_value_into_range() -> None:
    assert clamp(25.0, 17.0, 21.0) == 21.0
    assert clamp(15.0, 17.0, 21.0) == 17.0
    assert clamp(19.5, 17.0, 21.0) == 19.5


def test_compute_target_temperature_cheap_price_is_clamped_to_max() -> None:
    result = compute_target_temperature(price=3.0, indoor_temperature=20.0, constants=_constants())
    assert result == 21.0


def test_compute_target_temperature_expensive_price_reduces_target() -> None:
    result = compute_target_temperature(price=7.0, indoor_temperature=22.0, constants=_constants())
    assert result == 19.52


def test_compute_target_temperature_is_clamped_between_tmin_tmax() -> None:
    low = compute_target_temperature(price=99.0, indoor_temperature=21.0, constants=_constants())
    high = compute_target_temperature(price=-99.0, indoor_temperature=19.0, constants=_constants())

    assert low == 17.0
    assert high == 21.0


def test_compute_target_temperature_enforces_storage_protection_floor() -> None:
    result = compute_target_temperature(
        price=100.0, indoor_temperature=18.0, constants=_constants()
    )
    assert result == 18.0


