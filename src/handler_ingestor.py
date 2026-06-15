from __future__ import annotations

from typing import Any

from application.electricity_price_service import ElectricityPriceService
from config.settings import IngestorSettings


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entrypoint. 
    Ingests electricity price data and stores it in S3 for later use by optimizer."""

    settings = IngestorSettings.from_env()
    service = ElectricityPriceService(settings)
    result = service.handle(event)
    return {
        "statusCode": result.status_code,
        "headers": {"Content-Type": "application/json"},
        "body": result.body,
    }
