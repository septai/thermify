"""S3 adapter for generic JSON reads/writes and price retrieval."""

from __future__ import annotations

import json
import logging
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from application.errors import (
    S3DataRetrievalError,
    S3DataValidationError,
)

LOGGER = logging.getLogger()


class S3Client:
    """Reads and writes JSON data in S3."""

    def __init__(self, region_name: str, s3_client: Any | None = None) -> None:
        self._s3 = s3_client or boto3.client("s3", region_name=region_name)

    def read_json(self, bucket: str, key: str) -> Any:
        """Read and deserialize JSON payload from an S3 object."""
        try:
            response = self._s3.get_object(Bucket=bucket, Key=key)
            body = response["Body"].read().decode("utf-8")
            return json.loads(body)
        except (BotoCoreError, ClientError) as exc:
            raise S3DataRetrievalError(
                f"Failed to read JSON data from s3://{bucket}/{key}"
            ) from exc
        except (KeyError, TypeError, ValueError, UnicodeDecodeError) as exc:
            raise S3DataValidationError("S3 data payload is not valid JSON") from exc

    def write_json(self, bucket: str, key: str, payload: Any) -> None:
        """Serialize and write JSON payload to an S3 object."""
        try:
            body = json.dumps(payload).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise S3DataValidationError("S3 data payload is not JSON serializable") from exc

        try:
            self._s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json")
        except (BotoCoreError, ClientError) as exc:
            raise S3DataRetrievalError(f"Failed to write JSON data to s3://{bucket}/{key}") from exc

