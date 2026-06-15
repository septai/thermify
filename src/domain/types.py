from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict


class PriceEntry(TypedDict):
    price: float
    startDate: str
    endDate: str


class HeatingHistoryEntry(TypedDict):
    is_heating: bool
    startDate: str
    endDate: str


class ElectricityPricePayload(TypedDict):
    prices: list[PriceEntry]


@dataclass(slots=True)
class CozifyJsonConfig:
    """Parsed Cozify configuration from JSON in SSM Parameter Store."""
    # version: int
    cloud_token: str
    hub_id: str
    hub_key: str | None
    hub_name: str
    hub_host: str | None
    remote: bool
    email: str
    temperature_sensor_id: str
    last_refresh_timestamp_unix_ms: int | None
