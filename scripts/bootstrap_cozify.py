"""Interactive local CLI to bootstrap Cozify config into AWS SSM."""

from __future__ import annotations

import argparse
import base64
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from getpass import getpass
from typing import Any

import boto3
import requests

COZIFY_CLOUD_API_BASE = "https://api.cozify.fi/ui/0.2"
REQUEST_TIMEOUT_SECONDS = 10.0


@dataclass(slots=True)
class HubChoice:
    hub_id: str
    hub_key: str
    hub_name: str
    role: str | None
    owner: bool | None
    email: str | None


@dataclass(slots=True)
class SensorCandidate:
    device_id: str
    name: str
    device_type: str
    room: str
    reachable: bool | None
    temperature: float
    manufacturer: str
    model: str


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap Cozify onboarding and write config JSON to SSM"
    )
    parser.add_argument(
        "--parameter-name",
        help="Target SSM parameter name for Cozify config JSON (SecureString)",
    )
    parser.add_argument(
        "--region",
        default="eu-west-1",
        help="AWS region for SSM write (default: eu-west-1)",
    )
    parser.add_argument("--email", help="Cozify account email (otherwise prompted)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print resulting config JSON without writing to SSM",
    )
    return parser.parse_args()


def _derive_api_version(version: str) -> str:
    parts = [part for part in version.split(".") if part]
    if len(parts) < 2:
        return version.strip()
    return ".".join(parts[:2])


def _decode_hub_key_payload(hub_key: str) -> dict[str, object]:
    """Best-effort decode of JWT payload from hub key, returns empty dict on failure."""
    try:
        parts = hub_key.split(".")
        if len(parts) < 2:
            return {}
        payload_segment = parts[1]
        padded = payload_segment + "=" * (-len(payload_segment) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(decoded.decode("utf-8"))
        if isinstance(payload, dict):
            return payload
    except Exception:
        return {}
    return {}


def _build_hub_choices(hubkeys_payload: dict[str, Any]) -> list[HubChoice]:
    choices: list[HubChoice] = []
    for hub_id, hub_key in sorted(hubkeys_payload.items()):
        if not isinstance(hub_id, str) or not hub_id.strip():
            continue
        if not isinstance(hub_key, str) or not hub_key.strip():
            continue
        payload = _decode_hub_key_payload(hub_key)
        role_value = payload.get("role")
        role = role_value if isinstance(role_value, str) else None
        hub_name_value = payload.get("hubName")
        hub_name = hub_name_value if isinstance(hub_name_value, str) else hub_id
        owner_value = payload.get("owner")
        owner = owner_value if isinstance(owner_value, bool) else None
        email_value = payload.get("email")
        email = email_value if isinstance(email_value, str) else None
        choices.append(
            HubChoice(
                hub_id=hub_id,
                hub_key=hub_key,
                hub_name=hub_name,
                role=role,
                owner=owner,
                email=email,
            )
        )
    return choices


def _room_to_string(room_value: Any) -> str:
    if isinstance(room_value, str):
        return room_value
    if isinstance(room_value, list):
        parts = [item for item in room_value if isinstance(item, str) and item.strip()]
        if parts:
            return ",".join(parts)
    return "-"


def _filter_temperature_sensors(devices: dict[str, Any]) -> list[SensorCandidate]:
    candidates: list[SensorCandidate] = []
    for device_id, device in sorted(devices.items()):
        if not isinstance(device_id, str) or not isinstance(device, dict):
            continue

        capabilities = device.get("capabilities")
        capability_values = capabilities.get("values") if isinstance(capabilities, dict) else None
        if not isinstance(capability_values, list) or "TEMPERATURE" not in capability_values:
            continue

        state = device.get("state")
        if not isinstance(state, dict):
            continue
        temperature = state.get("temperature")
        if not isinstance(temperature, (int, float)):
            continue

        reachable = state.get("reachable") if isinstance(state.get("reachable"), bool) else None
        name_value = device.get("name")
        name = name_value if isinstance(name_value, str) else device_id
        device_type_value = device.get("type")
        device_type = device_type_value if isinstance(device_type_value, str) else "-"
        manufacturer_value = device.get("manufacturer")
        manufacturer = manufacturer_value if isinstance(manufacturer_value, str) else "-"
        model_value = device.get("model")
        model = model_value if isinstance(model_value, str) else "-"
        room = _room_to_string(device.get("room"))

        candidates.append(
            SensorCandidate(
                device_id=device_id,
                name=name,
                device_type=device_type,
                room=room,
                reachable=reachable,
                temperature=float(temperature),
                manufacturer=manufacturer,
                model=model,
            )
        )

    return candidates


def _select_by_index_or_id(selection: str, ids: list[str]) -> str:
    trimmed = selection.strip()
    if not trimmed:
        raise ValueError("Selection cannot be empty")

    if trimmed in ids:
        return trimmed

    if trimmed.isdigit():
        index = int(trimmed)
        if 1 <= index <= len(ids):
            return ids[index - 1]

    raise ValueError("Selection must be a listed index or id")


def _build_final_config(
    *,
    cloud_token: str,
    hub_id: str,
    hub_key: str,
    hub_name: str,
    email: str,
    temperature_sensor_id: str,
    timestamp_unix_ms: int,
) -> dict[str, Any]:
    return {
        # "version": 1,
        "cloud_token": cloud_token,
        "hub_id": hub_id,
        "hub_key": hub_key,
        "hub_name": hub_name,
        "hub_host": None,
        "remote": True,
        "email": email,
        "temperature_sensor_id": temperature_sensor_id,
        "last_refresh_timestamp_unix_ms": timestamp_unix_ms,
    }


def _request(
    session: requests.Session,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
) -> requests.Response:
    response = session.request(
        method,
        f"{COZIFY_CLOUD_API_BASE}{path}",
        headers=headers,
        params=params,
        json=json_body,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response


def _prompt_non_empty(prompt: str) -> str:
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("Input cannot be empty.")


def _normalize_parameter_name(parameter_name: str) -> str:
    """Normalize parameter name into SSM fully qualified path form.

    This also mitigates Git Bash / MSYS argument conversion where values like
    /lambda/cozify/config can be rewritten into Windows-style paths.
    """
    normalized = parameter_name.strip().replace("\\", "/")
    if not normalized:
        raise ValueError("Parameter name cannot be empty")

    # Git Bash may rewrite /lambda/... into something like C:/.../lambda/...
    if re.match(r"^[a-zA-Z]:/", normalized):
        lowered = normalized.lower()
        marker = "/lambda/"
        marker_index = lowered.find(marker)
        if marker_index >= 0:
            normalized = normalized[marker_index:]

    if not normalized.startswith("/"):
        normalized = f"/{normalized}"

    # Collapse duplicate slashes while preserving leading slash.
    parts = [part for part in normalized.split("/") if part]
    normalized = "/" + "/".join(parts)

    return normalized


def _choose_hub(hub_choices: list[HubChoice]) -> HubChoice:
    print("\nAvailable hubs:")
    for index, hub in enumerate(hub_choices, start=1):
        owner_text = "?" if hub.owner is None else str(hub.owner)
        print(
            f"  [{index}] id={hub.hub_id} name={hub.hub_name} role={hub.role or '-'} "
            f"owner={owner_text} email={hub.email or '-'}"
        )

    ids = [hub.hub_id for hub in hub_choices]
    while True:
        selection = _prompt_non_empty("Select hub by index or hub_id: ")
        try:
            selected_id = _select_by_index_or_id(selection, ids)
        except ValueError as exc:
            print(str(exc))
            continue
        for hub in hub_choices:
            if hub.hub_id == selected_id:
                return hub


def _choose_sensor(candidates: list[SensorCandidate]) -> SensorCandidate:
    print("\nTemperature sensor candidates:")
    for index, sensor in enumerate(candidates, start=1):
        print(
            f"  [{index}] id={sensor.device_id} name={sensor.name} type={sensor.device_type} "
            f"room={sensor.room} reachable={sensor.reachable} temp={sensor.temperature:.2f}C "
            f"manufacturer={sensor.manufacturer} model={sensor.model}"
        )

    ids = [sensor.device_id for sensor in candidates]
    while True:
        selection = _prompt_non_empty("Select temperature sensor by index or id: ")
        try:
            selected_id = _select_by_index_or_id(selection, ids)
        except ValueError as exc:
            print(str(exc))
            continue
        for sensor in candidates:
            if sensor.device_id == selected_id:
                return sensor


def _write_secure_string_parameter(parameter_name: str, region_name: str, value: str) -> None:
    ssm = boto3.client("ssm", region_name=region_name)
    ssm.put_parameter(
        Name=parameter_name,
        Value=value,
        Type="SecureString",
        Overwrite=True,
    )


def _run() -> int:
    args = _parse_args()
    email = (args.email or "").strip() or _prompt_non_empty("Cozify email: ")
    parameter_name = args.parameter_name
    if not args.dry_run and not parameter_name:
        parameter_name = _prompt_non_empty("SSM parameter name for Cozify config: ")

    if parameter_name:
        parameter_name = _normalize_parameter_name(parameter_name)

    session = requests.Session()

    print("Requesting one-time login code...")
    _request(session, "POST", "/user/requestlogin", params={"email": email})

    password = getpass("OTP/password from email: ").strip()
    if not password:
        print("OTP/password cannot be empty.")
        return 1

    print("Logging in to Cozify...")
    login_response = _request(
        session,
        "POST",
        "/user/emaillogin",
        json_body={"email": email, "password": password},
    )
    cloud_token = login_response.text.strip()
    if not cloud_token:
        print("Cozify did not return a cloud token.")
        return 1

    hubkeys_response = _request(
        session,
        "GET",
        "/user/hubkeys",
        headers={"Authorization": cloud_token},
    )
    hubkeys_payload = hubkeys_response.json()
    if not isinstance(hubkeys_payload, dict):
        print("Unexpected hubkeys payload from Cozify.")
        return 1

    hub_choices = _build_hub_choices(hubkeys_payload)
    if not hub_choices:
        print("No hubs available for this Cozify account.")
        return 1

    selected_hub = _choose_hub(hub_choices)
    remote_headers = {
        "Authorization": cloud_token,
        "X-Hub-Key": selected_hub.hub_key,
    }

    metadata_response = _request(
        session,
        "GET",
        "/hub/remote/hub",
        headers=remote_headers,
    )
    metadata_payload = metadata_response.json()
    if not isinstance(metadata_payload, dict):
        print("Unexpected hub metadata payload from Cozify.")
        return 1

    version = metadata_payload.get("version")
    if not isinstance(version, str) or not version.strip():
        print("Hub metadata is missing version.")
        return 1
    api_version = _derive_api_version(version)
    hub_name = metadata_payload.get("name")
    if not isinstance(hub_name, str) or not hub_name.strip():
        hub_name = selected_hub.hub_name

    devices_response = _request(
        session,
        "GET",
        f"/hub/remote/cc/{api_version}/devices",
        headers=remote_headers,
    )
    devices_payload = devices_response.json()
    if not isinstance(devices_payload, dict):
        print("Unexpected devices payload from Cozify.")
        return 1

    candidates = _filter_temperature_sensors(devices_payload)
    if not candidates:
        print("No temperature sensors found with numeric state.temperature.")
        return 1

    selected_sensor = _choose_sensor(candidates)
    now_unix_ms = int(datetime.now(UTC).timestamp() * 1000)
    config_dict = _build_final_config(
        cloud_token=cloud_token,
        hub_id=selected_hub.hub_id,
        hub_key=selected_hub.hub_key,
        hub_name=hub_name,
        email=email,
        temperature_sensor_id=selected_sensor.device_id,
        timestamp_unix_ms=now_unix_ms,
    )
    config_json = json.dumps(config_dict, separators=(",", ":"))

    if args.dry_run:
        print("\nDry run mode enabled. Generated config JSON:")
        print(json.dumps(config_dict, indent=2))
        return 0

    if not parameter_name:
        print("Parameter name is required unless --dry-run is used.")
        return 1

    _write_secure_string_parameter(parameter_name, args.region, config_json)
    print(f"Cozify config written to SSM SecureString parameter: {parameter_name}")
    return 0


def main() -> None:
    try:
        raise SystemExit(_run())
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        print(f"HTTP request failed with status {status}: {exc}")
        raise SystemExit(1) from exc
    except requests.RequestException as exc:
        print(f"Network request failed: {exc}")
        raise SystemExit(1) from exc
    except Exception as exc:
        print(f"Bootstrap failed: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
