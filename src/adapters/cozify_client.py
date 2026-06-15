"""Cozify adapter for reading indoor temperature."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import requests

from application.errors import CozifyAuthenticationError, CozifyDataError
from config.cozify_config import parse_cozify_json_config

COZIFY_CLOUD_API_BASE = "https://api.cozify.fi/ui/0.2"
REQUEST_TIMEOUT_SECONDS = 10.0
CONFIG_REFRESH_INTERVAL = timedelta(days=14)
CONFIG_VALIDITY_PERIOD = timedelta(days=28)
CONFIG_REFRESH_INTERVAL_MS = int(CONFIG_REFRESH_INTERVAL.total_seconds() * 1000)
CONFIG_VALIDITY_PERIOD_MS = int(CONFIG_VALIDITY_PERIOD.total_seconds() * 1000)

LOGGER = logging.getLogger()


class CozifyClient:
    """Reads indoor temperature from Cozify hub temperature sensors."""

    def __init__(
        self,
        config_text: str,
        parameter_store: Any | None = None,
        parameter_name: str | None = None,
    ) -> None:
        self._config = parse_cozify_json_config(config_text)
        self._session = requests.Session()
        self._api_version: str | None = None
        self._cloud_token = self._config.cloud_token
        self._hub_key = self._config.hub_key
        self._last_refresh_timestamp_unix_ms = self._config.last_refresh_timestamp_unix_ms
        self._parameter_store = parameter_store
        self._parameter_name = parameter_name

    def get_room_temperature(self, sensor_id: str) -> float:
        """Read temperature for the given sensor id."""
        if self._is_remote_mode():
            LOGGER.info("Reading indoor temperature from Cozify in remote mode")
            self._refresh_cloud_token_if_needed()
            self._ensure_remote_api_version()
            devices = self._get_remote_devices()
        else:
            LOGGER.info("Reading indoor temperature from Cozify in local mode")
            self._ensure_local_api_version()
            devices = self._get_local_devices()

        try:
            sensor = devices[sensor_id]
            temperature = sensor["state"]["temperature"]
        except Exception as exc:  # noqa: BLE001 - remote payloads are dynamic
            raise CozifyDataError(
                f"Failed to read temperature for Cozify sensor '{sensor_id}'"
            ) from exc

        try:
            return float(temperature)
        except (TypeError, ValueError) as exc:
            raise CozifyDataError(
                f"Failed to read temperature for Cozify sensor '{sensor_id}'"
            ) from exc

    def get_configured_temperature_sensor_id(self) -> str:
        """Return temperature sensor id from parsed Cozify JSON config."""
        return self._config.temperature_sensor_id

    def _is_remote_mode(self) -> bool:
        return self._config.remote

    def _refresh_cloud_token_if_needed(self) -> None:
        if self._cloud_token is None:
            raise CozifyAuthenticationError("1. Failed to authenticate to Cozify API")

        if not self._is_config_refresh_due():
            return

        if self._last_refresh_timestamp_unix_ms is not None:
            age_ms = _now_unix_ms() - self._last_refresh_timestamp_unix_ms
            if age_ms >= CONFIG_VALIDITY_PERIOD_MS:
                LOGGER.warning(
                    "Cozify config age (%s days) exceeded 28-day validity window; "
                    "manual refresh required - run bootstrap_cozify.py script "
                    "to recreate the expired token",
                    round(age_ms / (24 * 60 * 60 * 1000), 1),
                )

        # Refresh is due: attempt refresh even if token age exceeded validity window.
        # If refresh fails (for example token is permanently expired), caller handles
        # authentication/data failures and falls back to nominal target temperature.

        old_token = self._cloud_token
        try:
            refreshed_token = self._refresh_cloud_token(old_token)
        except CozifyDataError as exc:
            LOGGER.exception("Failed to refresh Cozify cloud token: " + str(exc))
            return

        self._cloud_token = refreshed_token
        self._invalidate_token_best_effort(old_token)
        self._persist_token_to_ssm()

    def _is_config_refresh_due(self) -> bool:
        last_refresh = self._last_refresh_timestamp_unix_ms
        if last_refresh is None:
            return True

        return _now_unix_ms() - last_refresh >= CONFIG_REFRESH_INTERVAL_MS

    def _refresh_cloud_token(self, token: str) -> str:
        response = self._request(
            "GET",
            f"{COZIFY_CLOUD_API_BASE}/user/refreshsession",
            headers={"Authorization": token},
        )

        if response.status_code == 200:
            LOGGER.info("Cozify cloud token refreshed successfully")
            return response.text.strip()
        raise CozifyDataError(f"Refresh failed with status code {response.status_code}")

    def _invalidate_token_best_effort(self, token: str) -> None:
        try:
            response = self._request(
                "PUT",
                f"{COZIFY_CLOUD_API_BASE}/user/logout",
                headers={"Authorization": token},
            )
            if response.status_code == 200:
                LOGGER.info("Old Cozify cloud token invalidated successfully")
            else:
                LOGGER.warning(
                    "Failed to invalidate old Cozify cloud token: "
                    f"unexpected status code {response.status_code}"
                )
        except CozifyAuthenticationError:
            LOGGER.warning("Failed to invalidate old Cozify cloud token: authentication error")
            pass
        except CozifyDataError:
            LOGGER.warning("Failed to invalidate old Cozify cloud token: data error")
            pass

    def _persist_token_to_ssm(self) -> None:
        """Persist refreshed token to SSM."""
        if not self._parameter_store or not self._parameter_name:
            LOGGER.warning(
                "Parameter store or parameter name not configured; "
                "skipping Cozify config persistence to SSM"
            )
            return

        now_unix_ms = _now_unix_ms()

        # Serialize updated config with new token and timestamp
        config_dict = self._serialize_config_for_ssm(now_unix_ms)

        # Persist to SSM
        self._parameter_store.put_secure_parameter(self._parameter_name, config_dict)
        self._last_refresh_timestamp_unix_ms = now_unix_ms
        LOGGER.info("Persisted refreshed Cozify config to SSM parameter")

    def _serialize_config_for_ssm(self, timestamp_unix_ms: int) -> dict[str, Any]:
        """Serialize current config state to dict for SSM storage."""
        return {
            # "version": 1,
            "cloud_token": self._cloud_token,
            "hub_id": self._config.hub_id,
            "hub_key": self._hub_key,
            "hub_name": self._config.hub_name,
            "hub_host": self._config.hub_host,
            "remote": self._config.remote,
            "email": self._config.email,
            "temperature_sensor_id": self._config.temperature_sensor_id,
            "last_refresh_timestamp_unix_ms": timestamp_unix_ms,
        }

    def _get_remote_hub_metadata(self) -> dict[str, Any]:
        hub_key = self._resolve_hub_key()
        headers = self._remote_headers(hub_key)
        response = self._request(
            "GET",
            f"{COZIFY_CLOUD_API_BASE}/hub/remote/hub",
            headers=headers,
        )
        return _parse_json_object(response.text, "Cozify hub metadata")

    def _get_remote_devices(self) -> dict[str, Any]:
        hub_key = self._resolve_hub_key()
        if self._api_version is None:
            raise CozifyDataError("Cozify api version is missing")
        response = self._request(
            "GET",
            f"{COZIFY_CLOUD_API_BASE}/hub/remote/cc/{self._api_version}/devices",
            headers=self._remote_headers(hub_key),
        )
        return _parse_json_object(response.text, "Cozify device list")

    def _get_local_hub_metadata(self) -> dict[str, Any]:
        if not self._config.hub_host:
            raise CozifyDataError("Cozify hub host is missing")

        response = self._request("GET", f"http://{self._config.hub_host}:8893/hub")
        return _parse_json_object(response.text, "Cozify hub metadata")

    def _ensure_remote_api_version(self) -> None:
        if self._api_version is not None:
            return

        metadata = self._get_remote_hub_metadata()
        self._api_version = _resolve_api_version_from_hub_metadata(metadata)

    def _ensure_local_api_version(self) -> None:
        if self._api_version is not None:
            return

        metadata = self._get_local_hub_metadata()
        self._api_version = _resolve_api_version_from_hub_metadata(metadata)

    def _get_local_devices(self) -> dict[str, Any]:
        if not self._config.hub_host:
            raise CozifyDataError("Cozify hub host is missing")

        if self._api_version is None:
            raise CozifyDataError("Cozify api version is missing")
        response = self._request(
            "GET",
            f"http://{self._config.hub_host}:8893/cc/{self._api_version}/devices",
        )
        return _parse_json_object(response.text, "Cozify device list")

    def _resolve_hub_key(self) -> str:
        if self._hub_key:
            return self._hub_key

        if not self._config.hub_id:
            raise CozifyDataError("Cozify hub id is missing")

        if self._cloud_token is None:
            raise CozifyAuthenticationError(
                "Cloud token is missing. Failed to authenticate to Cozify API"
            )

        response = self._request(
            "GET",
            f"{COZIFY_CLOUD_API_BASE}/user/hubkeys",
            headers={"Authorization": self._cloud_token},
        )
        hub_keys = _parse_json_object(response.text, "Cozify hub keys")
        hub_key = hub_keys.get(self._config.hub_id)
        if not isinstance(hub_key, str) or not hub_key.strip():
            raise CozifyDataError(f"No Cozify HubKey found for hub '{self._config.hub_id}'")

        self._hub_key = hub_key
        return hub_key

    def _remote_headers(self, hub_key: str) -> dict[str, str]:
        if self._cloud_token is None:
            raise CozifyAuthenticationError(
                "Cloud token is missing. Failed to authenticate to Cozify API"
            )

        return {
            "Authorization": self._cloud_token,
            "X-Hub-Key": hub_key,
        }

    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> requests.Response:
        try:
            response = self._session.request(
                method,
                url,
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise CozifyDataError("Failed to communicate with Cozify API") from exc

        if response.status_code in {401, 403}:
            raise CozifyAuthenticationError("4. Failed to authenticate to Cozify API")

        if not response.ok:
            raise CozifyDataError(f"Cozify API request failed with HTTP {response.status_code}")

        return response


def _parse_json_object(response_text: str, description: str) -> dict[str, Any]:
    try:
        decoded = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise CozifyDataError(f"Failed to parse {description} from Cozify API") from exc

    if not isinstance(decoded, dict):
        raise CozifyDataError(f"Failed to parse {description} from Cozify API")

    return decoded


def _now_unix_ms() -> int:
    """Get current time as Unix milliseconds."""
    return int(datetime.now(UTC).timestamp() * 1000)


def _derive_api_version(version: str) -> str:
    parts = [part for part in version.split(".") if part]
    if len(parts) < 2:
        return version.strip()
    return ".".join(parts[:2])


def _resolve_api_version_from_hub_metadata(metadata: dict[str, Any]) -> str:
    version = metadata.get("version")
    if not isinstance(version, str) or not version.strip():
        raise CozifyDataError("Cozify hub metadata is missing a version")

    return _derive_api_version(version)
