"""AWS Lambda entrypoint for price-driven Thermia heat-pump temperature control."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from adapters.cozify_client import CozifyClient
from adapters.parameter_store import ParameterStoreClient
from adapters.s3_client import S3Client
from adapters.thermia_client import ThermiaClient
from application.heating_control_service import (
    FallbackReason,
    HeatingControlService,
)
from config.settings import OptimizerSettings

LOGGER = logging.getLogger()
FALLBACK_METRIC_NAMESPACE = "Thermia/OptimizeHeating"
ERROR_METRIC_NAME = "ApplicationErrorCount"


def create_heating_control_service(settings: OptimizerSettings) -> HeatingControlService:
    """Factory to build service with runtime dependencies."""
    parameter_store_client = ParameterStoreClient(
        region_name=settings.aws_region,
    )
    s3_client = S3Client(region_name=settings.aws_region)

    thermia_username = parameter_store_client.get_secure_parameter(
        settings.thermia_username_parameter
    )
    thermia_password = parameter_store_client.get_secure_parameter(
        settings.thermia_password_parameter
    )
    cozify_config = parameter_store_client.get_secure_parameter(settings.cozify_config_parameter)

    thermia_client = ThermiaClient(
        thermia_username,
        thermia_password,
        demo_mode=settings.thermia_demo_mode,
    )
    cozify_client = CozifyClient(
        cozify_config, parameter_store_client, settings.cozify_config_parameter
    )

    return HeatingControlService(
        settings=settings,
        s3_client=s3_client,
        thermia_client=thermia_client,
        cozify_client=cozify_client,
    )


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def _emit_error_metric(
    settings: OptimizerSettings | None,
    failure_type: str,
    exc: Exception | None = None,
) -> None:
    if settings is None:
        LOGGER.warning(
            "Failed to emit CloudWatch metric %s: settings unavailable (error: %s)",
            ERROR_METRIC_NAME,
            str(exc) if exc is not None else failure_type,
        )
        return

    function_name = os.getenv("AWS_LAMBDA_FUNCTION_NAME", "unknown")

    LOGGER.info(
        "Emitting CloudWatch metric %s for failure type %s in function %s",
        ERROR_METRIC_NAME,
        failure_type,
        function_name,
    )

    try:
        cloudwatch = boto3.client("cloudwatch", region_name=settings.aws_region)
        cloudwatch.put_metric_data(
            Namespace=FALLBACK_METRIC_NAMESPACE,
            MetricData=[
                {
                    "MetricName": ERROR_METRIC_NAME,
                    "Dimensions": [
                        {
                            "Name": "FunctionName",
                            "Value": function_name,
                        },
                    ],
                    "Unit": "Count",
                    "Value": 1.0,
                }
            ],
        )
    except (
        BotoCoreError,
        ClientError,
        KeyError,
        TypeError,
        ValueError,
        RuntimeError,
    ) as metric_exc:
        LOGGER.warning(
            "Failed to emit CloudWatch metric %s: %s",
            ERROR_METRIC_NAME,
            str(metric_exc),
        )


def _try_ingest_price_data_to_s3() -> None:
    """Attempt to invoke the price data ingestor Lambda asynchronously to refresh S3 data."""
    lambda_client = boto3.client("lambda", region_name=os.getenv("AWS_REGION"))
    payload = {}
    # Invoke the ingestor Lambda asynchronously (Event invocation type)
    try:
        response = lambda_client.invoke(
            FunctionName="ingest-spot-prices",
            InvocationType="Event",
            Payload=json.dumps(payload),
        )
        LOGGER.info(
            "Async invocation of 'ingest-spot-prices' lambda queued with status code: %s",
            response["StatusCode"],
        )

    except Exception as exc:
        LOGGER.warning(
            "Failed to invoke 'ingest-spot-prices' lambda: %s",
            str(exc),
        )


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Compute and apply target temperature for the first Thermia heat pump."""
    request_id = getattr(context, "aws_request_id", None)

    try:
        settings = OptimizerSettings.from_env()
        LOGGER.setLevel(settings.log_level)

        service = create_heating_control_service(settings)
        result = service.execute()

        LOGGER.info(
            (
                "Heating control decision: price_snt_per_kwh=%s "
                "indoor_temperature_c=%s outdoor_temperature_c=%s "
                "target_temperature_c=%s "
                "fallback_used=%s fallback_reason=%s"
            ),
            result.price,
            result.indoor_temperature,
            result.outdoor_temperature,
            result.target_temperature,
            result.fallback_used,
            result.fallback_reason,
        )

        if result.fallback_used:
            if result.fallback_reason == FallbackReason.COZIFY_UNAVAILABLE:
                fallback_failure_type = "FallbackUsed-cozify_unavailable"
                LOGGER.warning(
                    "Cozify data unavailable."
                    "Attempt to run the script"
                    "'bootstrap_cozify.py' to resolve the issue."
                )
            elif result.fallback_reason == FallbackReason.PRICE_DATA_UNAVAILABLE:
                fallback_failure_type = "FallbackUsed-price_data_unavailable"
                _try_ingest_price_data_to_s3()
            else:
                fallback_failure_type = "FallbackUsed-unknown"
            _emit_error_metric(settings, fallback_failure_type)

        return _response(
            200,
            {
                "requestId": request_id,
                "message": "Target temperature applied successfully",
                "isSummer": result.is_summer,
                "priceSntPerKwh": result.price,
                "indoorTemperatureC": result.indoor_temperature,
                "outdoorTemperatureC": result.outdoor_temperature,
                "targetTemperatureC": result.target_temperature,
                "fallbackUsed": result.fallback_used,
                "fallbackReason": result.fallback_reason,
            },
        )
    except Exception as exc:
        LOGGER.exception("Failed to control Thermia target temperature: %s", str(exc))
        _emit_error_metric(locals().get("settings"), type(exc).__name__, exc)
        return _response(
            500,
            {
                "requestId": request_id,
                "message": "Failed to control Thermia target temperature",
            },
        )
