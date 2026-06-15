"""Secure parameter retrieval and storage via boto3 SSM."""

from __future__ import annotations

import json
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from application.errors import CredentialsRetrievalError


class ParameterStoreClient:
    """Reads and writes SecureString values in SSM Parameter Store."""

    def __init__(
        self,
        region_name: str,
        ssm_client: Any | None = None,
    ) -> None:
        self._ssm = ssm_client or boto3.client("ssm", region_name=region_name)

    def get_secure_parameter(self, parameter_name: str) -> str:
        """Read a SecureString parameter via boto3 SSM GetParameter."""
        try:
            response = self._ssm.get_parameter(Name=parameter_name, WithDecryption=True)
            return response["Parameter"]["Value"]
        except (BotoCoreError, ClientError, KeyError, TypeError, ValueError, RuntimeError) as exc:
            raise CredentialsRetrievalError(
                f"Failed to retrieve secure parameter '{parameter_name}'"
            ) from exc

    def put_secure_parameter(self, parameter_name: str, parameter_value: dict[str, Any]) -> None:
        """Write a SecureString parameter to SSM Parameter Store as JSON.

        Args:
            parameter_name: SSM parameter path (e.g., "/lambda/cozify/config").
            parameter_value: Dictionary to serialize.

        Note:
            Errors are logged but not raised (fail gracefully).
        """
        try:
            parameter_json = json.dumps(parameter_value, separators=(",", ":"))
            self._ssm.put_parameter(
                Name=parameter_name,
                Value=parameter_json,
                Type="SecureString",
                Overwrite=True,
            )
        except (BotoCoreError, ClientError, TypeError, ValueError) as exc:
            # Log but don't raise - SSM persistence is best-effort
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(
                "Failed to persist Cozify config to SSM parameter '%s': %s",
                parameter_name,
                str(exc),
            )
