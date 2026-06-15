"""JSON configuration parser for Cozify cloud and hub credentials."""

from __future__ import annotations

import json

from application.errors import CozifyDataError
from domain.types import CozifyJsonConfig


def parse_cozify_json_config(config_json: str) -> CozifyJsonConfig:
    """Parse Cozify configuration from JSON text.

    Args:
        config_json: JSON string containing Cozify configuration.

    Returns:
        Parsed configuration object.

    Raises:
        CozifyDataError: If JSON is empty, invalid, or missing required fields.
    """
    if not config_json.strip():
        raise CozifyDataError("Cozify config is empty")

    try:
        config_dict = json.loads(config_json)
    except json.JSONDecodeError as exc:
        raise CozifyDataError("Cozify config is not valid JSON") from exc

    if not isinstance(config_dict, dict):
        raise CozifyDataError("Cozify config is not a JSON object")

    # version = config_dict.get("version")
    # if version != 1:
    #     raise CozifyDataError(f"Cozify config version {version} is not supported (expected 1)")

    # Validate required fields
    required_fields = {"cloud_token", "hub_id", "hub_name", "email", "temperature_sensor_id"}
    missing_fields = required_fields - set(config_dict.keys())
    if missing_fields:
        raise CozifyDataError(
            f"Cozify config is missing required fields: {', '.join(sorted(missing_fields))}"
        )

    # Extract and validate cloud_token
    cloud_token = config_dict.get("cloud_token")
    if not isinstance(cloud_token, str) or not cloud_token.strip():
        raise CozifyDataError("Cozify config cloud_token must be a non-empty string")

    # Extract and validate hub_id
    hub_id = config_dict.get("hub_id")
    if not isinstance(hub_id, str) or not hub_id.strip():
        raise CozifyDataError("Cozify config hub_id must be a non-empty string")

    # Extract hub_key (optional for local access)
    hub_key = config_dict.get("hub_key")
    if hub_key is not None and not isinstance(hub_key, str):
        raise CozifyDataError("Cozify config hub_key must be a string or null")
    hub_key_str = hub_key if isinstance(hub_key, str) and hub_key.strip() else None

    # Extract and validate hub_name
    hub_name = config_dict.get("hub_name")
    if not isinstance(hub_name, str) or not hub_name.strip():
        raise CozifyDataError("Cozify config hub_name must be a non-empty string")

    # Extract hub_host (optional)
    hub_host = config_dict.get("hub_host")
    if hub_host is not None and not isinstance(hub_host, str):
        raise CozifyDataError("Cozify config hub_host must be a string or null")
    hub_host_str = hub_host if isinstance(hub_host, str) and hub_host.strip() else None

    # Extract and validate remote flag
    remote = config_dict.get("remote", True)
    if not isinstance(remote, bool):
        raise CozifyDataError("Cozify config remote must be a boolean")

    # Extract and validate email
    email = config_dict.get("email")
    if not isinstance(email, str) or not email.strip():
        raise CozifyDataError("Cozify config email must be a non-empty string")

    # Extract and validate temperature_sensor_id
    temp_sensor_id = config_dict.get("temperature_sensor_id")
    if not isinstance(temp_sensor_id, str) or not temp_sensor_id.strip():
        raise CozifyDataError("Cozify config temperature_sensor_id must be a non-empty string")

    # Extract optional timestamp field
    last_refresh_timestamp = config_dict.get("last_refresh_timestamp_unix_ms")
    if last_refresh_timestamp is not None and not isinstance(last_refresh_timestamp, int):
        raise CozifyDataError(
            "Cozify config last_refresh_timestamp_unix_ms must be an integer or null"
        )

    return CozifyJsonConfig(
        # version = 1,
        cloud_token=cloud_token.strip(),
        hub_id=hub_id.strip(),
        hub_key=hub_key_str,
        hub_name=hub_name.strip(),
        hub_host=hub_host_str,
        remote=remote,
        email=email.strip(),
        temperature_sensor_id=temp_sensor_id.strip(),
        last_refresh_timestamp_unix_ms=last_refresh_timestamp,
    )
