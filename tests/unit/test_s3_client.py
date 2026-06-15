import json
from datetime import UTC, datetime
from typing import Any

import pytest

from adapters.s3_client import S3Client
from application.errors import S3DataValidationError


class FakeBody:
    def __init__(self, data: str) -> None:
        self._bytes = data.encode("utf-8")

    def read(self) -> bytes:
        return self._bytes


class FakeS3Client:
    def __init__(self, payload: Any) -> None:
        self._payload = payload
        self.last_written_payload: dict[str, Any] | None = None

    def get_object(self, Bucket: str, Key: str) -> dict:
        _ = Bucket
        _ = Key
        return {"Body": FakeBody(json.dumps(self._payload))}

    def put_object(self, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:
        _ = Bucket
        _ = Key
        _ = ContentType
        self.last_written_payload = json.loads(Body.decode("utf-8"))


# def test_get_current_price_returns_matching_slot_price() -> None:
#     payload = {
#         "prices": [
#             {
#                 "price": 2.5,
#                 "startDate": "2026-04-23T10:00:00.000Z",
#                 "endDate": "2026-04-23T10:14:59.999Z",
#             },
#             {
#                 "price": 3.5,
#                 "startDate": "2026-04-23T10:15:00.000Z",
#                 "endDate": "2026-04-23T10:29:59.999Z",
#             },
#         ]
#     }
#     client = S3Client(region_name="eu-west-1", s3_client=FakeS3Client(payload))

#     price = client.get_current_price(
#         bucket="spot-electricity-prices-149796722280-eu-west-1-an",
#         key="latest-prices.json",
#         now=datetime(2026, 4, 23, 10, 8, tzinfo=UTC),
#     )

#     assert price == 2.5


# def test_get_current_price_raises_when_current_slot_missing() -> None:
#     payload = {
#         "prices": [
#             {
#                 "price": 2.5,
#                 "startDate": "2026-04-23T10:00:00.000Z",
#                 "endDate": "2026-04-23T10:14:59.999Z",
#             }
#         ]
#     }
#     client = S3Client(region_name="eu-west-1", s3_client=FakeS3Client(payload))

#     with pytest.raises(S3DataValidationError):
#         client.get_current_price(
#             bucket="spot-electricity-prices-149796722280-eu-west-1-an",
#             key="latest-prices.json",
#             now=datetime(2026, 4, 23, 10, 30, tzinfo=UTC),
#         )


# def test_get_current_price_raises_when_payload_is_invalid() -> None:
#     client = S3Client(region_name="eu-west-1", s3_client=FakeS3Client({"invalid": []}))

#     with pytest.raises(S3DataValidationError):
#         client.get_current_price(
#             bucket="spot-electricity-prices-149796722280-eu-west-1-an",
#             key="latest-prices.json",
#             now=datetime(2026, 4, 23, 10, 0, tzinfo=UTC),
#         )


def test_read_json_returns_payload() -> None:
    payload = {
        "history": [
            {
                "is_heating": 1,
                "startDate": "2026-04-23T10:00:00Z",
                "endDate": "2026-04-23T10:14:59Z",
            }
        ]
    }
    client = S3Client(region_name="eu-west-1", s3_client=FakeS3Client(payload))

    result = client.read_json(
        bucket="spot-electricity-prices-149796722280-eu-west-1-an",
        key="heating-history.json",
    )

    assert result == payload


def test_write_json_serializes_payload() -> None:
    fake_s3 = FakeS3Client(payload={})
    client = S3Client(region_name="eu-west-1", s3_client=fake_s3)
    payload = {
        "history": [
            {
                "is_heating": 1,
                "startDate": "2026-04-23T10:00:00Z",
                "endDate": "2026-04-23T10:14:59Z",
            }
        ]
    }

    client.write_json(
        bucket="spot-electricity-prices-149796722280-eu-west-1-an",
        key="heating-history.json",
        payload=payload,
    )

    assert fake_s3.last_written_payload == payload
