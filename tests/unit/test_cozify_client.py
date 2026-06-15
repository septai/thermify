from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from adapters.cozify_client import CozifyClient
from application.errors import CozifyAuthenticationError, CozifyDataError


@dataclass
class FakeResponse:
    status_code: int = 200
    text: str = ""

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def request(self, method: str, url: str, **kwargs) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        if not self._responses:
            raise AssertionError(f"Unexpected request: {method} {url}")
        return self._responses.pop(0)


def _build_token(expiry: datetime) -> str:
    header = (
        base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode("utf-8"))
        .decode("ascii")
        .rstrip("=")
    )
    payload = (
        base64.urlsafe_b64encode(json.dumps({"exp": int(expiry.timestamp())}).encode("utf-8"))
        .decode("ascii")
        .rstrip("=")
    )
    return f"{header}.{payload}.signature"


def _build_config(
    *,
    cloud_token: str,
    hub_key: str,
    hub_id: str = "hub-123",
    last_refresh_unix_ms: int | None = None,
) -> str:
    """Build JSON Cozify configuration for testing."""
    config = {
        "cloud_token": cloud_token,
        "hub_id": hub_id,
        "hub_key": hub_key,
        "hub_name": "Test Hub",
        "hub_host": "192.168.1.24",
        "remote": True,
        "email": "test@example.com",
        "temperature_sensor_id": "sensor-1",
        "last_refresh_timestamp_unix_ms": last_refresh_unix_ms,
    }
    return json.dumps(config)


def test_get_room_temperature_returns_sensor_temperature_and_caches_version(monkeypatch) -> None:
    cloud_token = _build_token(datetime.now(UTC) + timedelta(days=30))
    last_refresh_unix_ms = int((datetime.now(UTC) - timedelta(days=1)).timestamp() * 1000)
    session = FakeSession(
        [
            FakeResponse(text=json.dumps({"hubId": "hub-123", "version": "1.14.12.20"})),
            FakeResponse(
                text=json.dumps(
                    {
                        "sensor-1": {"state": {"temperature": 20.8}},
                    }
                )
            ),
            FakeResponse(
                text=json.dumps(
                    {
                        "sensor-1": {"state": {"temperature": 21.1}},
                    }
                )
            ),
        ]
    )
    monkeypatch.setattr("adapters.cozify_client.requests.Session", lambda: session)

    client = CozifyClient(
        _build_config(
            cloud_token=cloud_token,
            hub_key="hub-key-1",
            last_refresh_unix_ms=last_refresh_unix_ms,
        ),
    )

    first_temperature = client.get_room_temperature("sensor-1")
    second_temperature = client.get_room_temperature("sensor-1")

    assert first_temperature == 20.8
    assert second_temperature == 21.1
    assert [call["url"] for call in session.calls] == [
        "https://api.cozify.fi/ui/0.2/hub/remote/hub",
        "https://api.cozify.fi/ui/0.2/hub/remote/cc/1.14/devices",
        "https://api.cozify.fi/ui/0.2/hub/remote/cc/1.14/devices",
    ]


def test_get_room_temperature_refreshes_token_when_last_refresh_is_14_plus_days_old(
    monkeypatch,
) -> None:
    old_token = _build_token(datetime.now(UTC) + timedelta(days=1))
    refreshed_token = _build_token(datetime.now(UTC) + timedelta(days=30))
    last_refresh_unix_ms = int((datetime.now(UTC) - timedelta(days=20)).timestamp() * 1000)
    session = FakeSession(
        [
            FakeResponse(text=refreshed_token),
            FakeResponse(status_code=204, text=""),
            FakeResponse(text=json.dumps({"hubId": "hub-123", "version": "1.14.12.20"})),
            FakeResponse(
                text=json.dumps(
                    {
                        "sensor-1": {"state": {"temperature": 19.5}},
                    }
                )
            ),
        ]
    )
    monkeypatch.setattr("adapters.cozify_client.requests.Session", lambda: session)

    client = CozifyClient(
        _build_config(
            cloud_token=old_token,
            hub_key="hub-key-1",
            last_refresh_unix_ms=last_refresh_unix_ms,
        ),
    )

    temperature = client.get_room_temperature("sensor-1")

    assert temperature == 19.5
    assert [call["url"] for call in session.calls] == [
        "https://api.cozify.fi/ui/0.2/user/refreshsession",
        "https://api.cozify.fi/ui/0.2/user/logout",
        "https://api.cozify.fi/ui/0.2/hub/remote/hub",
        "https://api.cozify.fi/ui/0.2/hub/remote/cc/1.14/devices",
    ]
    assert session.calls[0]["headers"] == {"Authorization": old_token}
    assert session.calls[1]["headers"] == {"Authorization": old_token}
    assert session.calls[2]["headers"] == {
        "Authorization": refreshed_token,
        "X-Hub-Key": "hub-key-1",
    }
    assert session.calls[3]["headers"] == {
        "Authorization": refreshed_token,
        "X-Hub-Key": "hub-key-1",
    }


def test_get_room_temperature_raises_on_missing_sensor(monkeypatch) -> None:
    cloud_token = _build_token(datetime.now(UTC) + timedelta(days=30))
    last_refresh_unix_ms = int((datetime.now(UTC) - timedelta(days=1)).timestamp() * 1000)
    session = FakeSession(
        [
            FakeResponse(text=json.dumps({"hubId": "hub-123", "version": "1.14.12.20"})),
            FakeResponse(text=json.dumps({})),
        ]
    )
    monkeypatch.setattr("adapters.cozify_client.requests.Session", lambda: session)

    client = CozifyClient(
        _build_config(
            cloud_token=cloud_token,
            hub_key="hub-key-1",
            last_refresh_unix_ms=last_refresh_unix_ms,
        )
    )

    with pytest.raises(CozifyDataError):
        client.get_room_temperature("missing-sensor")


def test_get_room_temperature_raises_on_refresh_auth_failure(monkeypatch) -> None:
    cloud_token = _build_token(datetime.now(UTC) + timedelta(days=1))
    last_refresh_unix_ms = int((datetime.now(UTC) - timedelta(days=20)).timestamp() * 1000)
    session = FakeSession([FakeResponse(status_code=401, text="")])
    monkeypatch.setattr("adapters.cozify_client.requests.Session", lambda: session)

    client = CozifyClient(
        _build_config(
            cloud_token=cloud_token,
            hub_key="hub-key-1",
            last_refresh_unix_ms=last_refresh_unix_ms,
        )
    )

    with pytest.raises(CozifyAuthenticationError):
        client.get_room_temperature("sensor-1")

    assert session.calls[0]["url"] == "https://api.cozify.fi/ui/0.2/user/refreshsession"


def test_get_room_temperature_attempts_refresh_when_config_is_older_than_28_days(
    monkeypatch,
) -> None:
    old_token = _build_token(datetime.now(UTC) + timedelta(days=1))
    refreshed_token = _build_token(datetime.now(UTC) + timedelta(days=30))
    last_refresh_unix_ms = int((datetime.now(UTC) - timedelta(days=35)).timestamp() * 1000)
    session = FakeSession(
        [
            FakeResponse(text=refreshed_token),
            FakeResponse(status_code=204, text=""),
            FakeResponse(text=json.dumps({"hubId": "hub-123", "version": "1.14.12.20"})),
            FakeResponse(
                text=json.dumps(
                    {
                        "sensor-1": {"state": {"temperature": 18.9}},
                    }
                )
            ),
        ]
    )
    monkeypatch.setattr("adapters.cozify_client.requests.Session", lambda: session)

    client = CozifyClient(
        _build_config(
            cloud_token=old_token,
            hub_key="hub-key-1",
            last_refresh_unix_ms=last_refresh_unix_ms,
        ),
    )

    temperature = client.get_room_temperature("sensor-1")

    assert temperature == 18.9
    assert [call["url"] for call in session.calls] == [
        "https://api.cozify.fi/ui/0.2/user/refreshsession",
        "https://api.cozify.fi/ui/0.2/user/logout",
        "https://api.cozify.fi/ui/0.2/hub/remote/hub",
        "https://api.cozify.fi/ui/0.2/hub/remote/cc/1.14/devices",
    ]


def test_get_room_temperature_persists_token_to_ssm_after_14_day_refresh(monkeypatch) -> None:
    """Test that SSM persistence is triggered after 14+ days since last refresh."""
    old_token = _build_token(datetime.now(UTC) + timedelta(days=1))
    refreshed_token = _build_token(datetime.now(UTC) + timedelta(days=30))

    # Last refresh was 20 days ago
    now_unix_ms = int(datetime.now(UTC).timestamp() * 1000)
    last_refresh_unix_ms = now_unix_ms - (20 * 24 * 60 * 60 * 1000)

    session = FakeSession(
        [
            FakeResponse(text=refreshed_token),
            FakeResponse(status_code=204, text=""),
            FakeResponse(text=json.dumps({"hubId": "hub-123", "version": "1.14.12.20"})),
            FakeResponse(
                text=json.dumps(
                    {
                        "sensor-1": {"state": {"temperature": 19.5}},
                    }
                )
            ),
        ]
    )
    monkeypatch.setattr("adapters.cozify_client.requests.Session", lambda: session)

    # Mock parameter store
    class FakeParameterStore:
        def __init__(self):
            self.put_calls = []

        def put_secure_parameter(self, param_name: str, config_dict: dict) -> None:
            self.put_calls.append({"param_name": param_name, "config": config_dict})

    param_store = FakeParameterStore()

    client = CozifyClient(
        _build_config(
            cloud_token=old_token,
            hub_key="hub-key-1",
            last_refresh_unix_ms=last_refresh_unix_ms,
        ),
        parameter_store=param_store,
        parameter_name="/lambda/cozify/config",
    )

    temperature = client.get_room_temperature("sensor-1")

    assert temperature == 19.5
    # Verify SSM persistence was called
    assert len(param_store.put_calls) == 1
    assert param_store.put_calls[0]["param_name"] == "/lambda/cozify/config"
    persisted_config = param_store.put_calls[0]["config"]
    assert persisted_config["cloud_token"] == refreshed_token
    assert persisted_config["hub_key"] == "hub-key-1"


def test_get_room_temperature_skips_ssm_persistence_if_less_than_14_days(monkeypatch) -> None:
    """Test that SSM persistence is NOT triggered if < 14 days since last refresh."""
    old_token = _build_token(datetime.now(UTC) + timedelta(days=1))

    # Last refresh was 10 days ago (< 14 days)
    now_unix_ms = int(datetime.now(UTC).timestamp() * 1000)
    last_refresh_unix_ms = now_unix_ms - (10 * 24 * 60 * 60 * 1000)

    session = FakeSession(
        [
            FakeResponse(text=json.dumps({"hubId": "hub-123", "version": "1.14.12.20"})),
            FakeResponse(
                text=json.dumps(
                    {
                        "sensor-1": {"state": {"temperature": 19.5}},
                    }
                )
            ),
        ]
    )
    monkeypatch.setattr("adapters.cozify_client.requests.Session", lambda: session)

    # Mock parameter store
    class FakeParameterStore:
        def __init__(self):
            self.put_calls = []

        def put_secure_parameter(self, param_name: str, config_dict: dict) -> None:
            self.put_calls.append({"param_name": param_name, "config": config_dict})

    param_store = FakeParameterStore()

    client = CozifyClient(
        _build_config(
            cloud_token=old_token,
            hub_key="hub-key-1",
            last_refresh_unix_ms=last_refresh_unix_ms,
        ),
        parameter_store=param_store,
        parameter_name="/lambda/cozify/config",
    )

    temperature = client.get_room_temperature("sensor-1")

    assert temperature == 19.5
    # Verify SSM persistence was NOT called (< 14 days)
    assert len(param_store.put_calls) == 0
