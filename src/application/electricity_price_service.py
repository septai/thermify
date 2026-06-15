from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from adapters.electricity_price_client import (
    ElectricityPriceClient,
    ElectricityPricePayload,
)
from adapters.s3_client import S3Client
from config.settings import IngestorSettings
from domain.interfaces import ElectricityPriceClientProtocol, S3ClientProtocol
from domain.types import PriceEntry


@dataclass(frozen=True, slots=True)
class ElectricityPriceServiceResult:
    status_code: int
    body: dict[str, Any]


class ElectricityPriceService:
    """Orchestrates electricity price fetch and S3 persistence."""

    def __init__(
        self,
        settings: IngestorSettings,
        price_client: ElectricityPriceClientProtocol | None = None,
        s3_client: S3ClientProtocol | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._settings = settings
        self._price_client = price_client or ElectricityPriceClient(
            settings.power_price_api_url
        )
        self._s3_client = s3_client or S3Client(region_name=settings.aws_region)
        
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def handle(self, _event: dict[str, Any]) -> ElectricityPriceServiceResult:
        payload = self._price_client.fetch_latest_prices()
        sorted_payload = ElectricityPricePayload(
            prices=self._sort_prices_by_start_date(payload["prices"])
        )
        generated_at = self._now_provider()
     
        self._s3_client.write_json(
            bucket = self._settings.s3_bucket,
            key = self._settings.s3_price_key,
            payload = sorted_payload)

        return ElectricityPriceServiceResult(
            status_code=200,
            body={
                "message": "ok",
                "bucket": self._settings.s3_bucket,
                "key": self._settings.s3_price_key,
                "priceCount": len(sorted_payload),
                "sourceUrl": self._settings.power_price_api_url,
                "savedAt": generated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )

    def _sort_prices_by_start_date(
        self, prices: list[PriceEntry]
    ) -> list[PriceEntry]:
        return sorted(prices, key=lambda price: price["startDate"])


