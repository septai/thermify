"""Pure domain logic for price-driven target temperature control."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TemperatureControlConstants:
    """Constants used in target temperature computation."""

    nominal_target_temperature: float
    nominal_indoor_temperature: float
    min_target_temperature: float
    max_target_temperature: float
    reference_price: float
    low_temperature_protection_margin: float
    price_gain: float
    indoor_temperature_gain: float
    low_temperature_boost: float


def clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp a numeric value into an inclusive [minimum, maximum] range."""
    if minimum > maximum:
        raise ValueError("minimum cannot be greater than maximum")
    return max(minimum, min(value, maximum))


def compute_target_temperature(
    price: float,
    indoor_temperature: float,
    constants: TemperatureControlConstants,
) -> float:
    """Compute new target temperature using price and indoor temperature."""
    price_adjustment = (constants.reference_price - price) / constants.reference_price
    indoor_temperature_adjustment = max(
        constants.nominal_indoor_temperature - indoor_temperature, 0.0
    )  # Only consider positive difference

    low_indoor_temperature_adjustment = max(
        constants.nominal_indoor_temperature
        - indoor_temperature
        - constants.low_temperature_protection_margin,
        0.0,
    )  # Only consider positive difference

    target_temperature = (
        constants.nominal_target_temperature
        + constants.price_gain * price_adjustment
        + constants.indoor_temperature_gain * indoor_temperature_adjustment
        + constants.low_temperature_boost * low_indoor_temperature_adjustment
    )

    # If indoor temperature is above nominal, don't allow target to exceed nominal
    if indoor_temperature > constants.nominal_indoor_temperature:
        target_temperature = min(target_temperature, constants.nominal_target_temperature)

    # If indoor temperature is significantly below nominal,
    # don't allow target to drop too low to protect storage
    if (
        indoor_temperature
        < constants.nominal_indoor_temperature - constants.low_temperature_protection_margin
    ):
        target_temperature = max(
            target_temperature,
            constants.nominal_target_temperature - constants.low_temperature_protection_margin,
        )

    return clamp(
        target_temperature, constants.min_target_temperature, constants.max_target_temperature
    )
