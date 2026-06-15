from __future__ import annotations

import base64
import importlib.util
import json
import sys
from pathlib import Path


def _load_bootstrap_module():
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "scripts" / "bootstrap_cozify.py"
    spec = importlib.util.spec_from_file_location("bootstrap_cozify", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Failed to load bootstrap module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _build_jwt(payload: dict[str, object]) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode("utf-8"))
    payload_encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8"))
    return f"{header.decode('ascii').rstrip('=')}.{payload_encoded.decode('ascii').rstrip('=')}.sig"


def test_decode_hub_key_payload_returns_payload_dict() -> None:
    module = _load_bootstrap_module()
    token = _build_jwt(
        {
            "hubName": "Main Hub",
            "role": "ADMIN",
            "owner": True,
            "email": "owner@example.com",
        }
    )

    payload = module._decode_hub_key_payload(token)

    assert payload["hubName"] == "Main Hub"
    assert payload["role"] == "ADMIN"
    assert payload["owner"] is True
    assert payload["email"] == "owner@example.com"


def test_decode_hub_key_payload_returns_empty_dict_for_invalid_token() -> None:
    module = _load_bootstrap_module()

    assert module._decode_hub_key_payload("not-a-jwt") == {}


def test_filter_temperature_sensors_keeps_only_numeric_temperature_candidates() -> None:
    module = _load_bootstrap_module()
    devices = {
        "sensor-1": {
            "id": "sensor-1",
            "name": "Indoor Sensor",
            "type": "MULTI_SENSOR",
            "room": ["living-room"],
            "manufacturer": "Acme",
            "model": "M1",
            "capabilities": {"values": ["DEVICE", "TEMPERATURE"]},
            "state": {"temperature": 21.5, "reachable": True},
        },
        "sensor-2": {
            "id": "sensor-2",
            "name": "No Numeric",
            "type": "MULTI_SENSOR",
            "room": ["bedroom"],
            "capabilities": {"values": ["TEMPERATURE"]},
            "state": {"temperature": "warm", "reachable": False},
        },
        "light-1": {
            "id": "light-1",
            "capabilities": {"values": ["DEVICE", "ON_OFF"]},
            "state": {"temperature": 20.0},
        },
    }

    candidates = module._filter_temperature_sensors(devices)

    assert len(candidates) == 1
    assert candidates[0].device_id == "sensor-1"
    assert candidates[0].temperature == 21.5
    assert candidates[0].room == "living-room"
    assert candidates[0].manufacturer == "Acme"
    assert candidates[0].model == "M1"


def test_select_by_index_or_id_accepts_both_input_styles() -> None:
    module = _load_bootstrap_module()
    ids = ["a", "b", "c"]

    assert module._select_by_index_or_id("2", ids) == "b"
    assert module._select_by_index_or_id("c", ids) == "c"


def test_select_by_index_or_id_rejects_invalid_value() -> None:
    module = _load_bootstrap_module()

    try:
        module._select_by_index_or_id("99", ["x"])
    except ValueError as exc:
        assert "listed index or id" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_build_final_config_matches_expected_schema() -> None:
    module = _load_bootstrap_module()

    config = module._build_final_config(
        cloud_token="cloud-token",
        hub_id="hub-1",
        hub_key="hub-key-1",
        hub_name="Home Hub",
        email="user@example.com",
        temperature_sensor_id="sensor-123",
        timestamp_unix_ms=1234567890000,
    )

    assert config == {
        "cloud_token": "cloud-token",
        "hub_id": "hub-1",
        "hub_key": "hub-key-1",
        "hub_name": "Home Hub",
        "hub_host": None,
        "remote": True,
        "email": "user@example.com",
        "temperature_sensor_id": "sensor-123",
        "last_refresh_timestamp_unix_ms": 1234567890000,
    }


def test_derive_api_version_uses_major_minor() -> None:
    module = _load_bootstrap_module()

    assert module._derive_api_version("1.14.12.20") == "1.14"
    assert module._derive_api_version("2") == "2"


def test_normalize_parameter_name_keeps_fully_qualified_name() -> None:
    module = _load_bootstrap_module()

    assert module._normalize_parameter_name("/lambda/cozify/config") == "/lambda/cozify/config"


def test_normalize_parameter_name_adds_missing_leading_slash() -> None:
    module = _load_bootstrap_module()

    assert module._normalize_parameter_name("lambda/cozify/config") == "/lambda/cozify/config"


def test_normalize_parameter_name_collapses_duplicate_slashes() -> None:
    module = _load_bootstrap_module()

    assert module._normalize_parameter_name("//lambda//cozify///config") == "/lambda/cozify/config"


def test_normalize_parameter_name_recovers_git_bash_converted_windows_path() -> None:
    module = _load_bootstrap_module()

    converted = "C:/Program Files/Git/lambda/cozify/configtest"
    assert module._normalize_parameter_name(converted) == "/lambda/cozify/configtest"


