from __future__ import annotations

import requests

from application.errors import ExternalApiError, InvalidApiResponseError
from domain.types import ElectricityPricePayload


class ElectricityPriceClient:
    """Fetches electricity prices from the public Porssisahko API."""

    def __init__(self, api_url: str, timeout_seconds: float = 10.0) -> None:
        self._api_url = api_url
        self._timeout_seconds = timeout_seconds

    def fetch_latest_prices(self) -> ElectricityPricePayload:
        try:
            response = requests.get(self._api_url, timeout=self._timeout_seconds)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ExternalApiError("Electricity price API request failed") from exc

        payload = response.json()
        if not isinstance(payload, dict):
            raise InvalidApiResponseError(
                "Expected JSON object from electricity price API"
            )

        prices = payload.get("prices")
        if not isinstance(prices, list):
            raise InvalidApiResponseError(
                "Expected 'prices' list in electricity price API payload"
            )

        for item in prices:
            if not isinstance(item, dict):
                raise InvalidApiResponseError("Each price item must be a JSON object")
            if not {"price", "startDate", "endDate"}.issubset(item.keys()):
                raise InvalidApiResponseError(
                    "Price item is missing required fields: price, startDate, endDate"
                )

        return ElectricityPricePayload(prices=prices)
