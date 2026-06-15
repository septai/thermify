import json

import handler_optimizer
from application.errors import ApplicationError
from application.heating_control_service import HeatingControlResult


class DummyContext:
    aws_request_id = "req-123"


class FakeLambdaClient:
    def invoke(self, FunctionName: str, InvocationType: str, Payload: str) -> dict[str, int]:
        assert FunctionName == "ingest-spot-prices"
        assert InvocationType == "Event"
        _ = Payload
        return {"StatusCode": 202}


class DummyService:
    def execute(self):
        return HeatingControlResult(
            is_summer=False,
            price=2.5,
            indoor_temperature=20.7,
            outdoor_temperature=5.0,
            target_temperature=20.3,
            fallback_used=False,
            fallback_reason=None,
        )


class CozifyUnavailableFallbackService:
    def execute(self):
        return HeatingControlResult(
            is_summer=False,
            price=2.5,
            indoor_temperature=None,
            outdoor_temperature=5.0,
            target_temperature=20.0,
            fallback_used=True,
            fallback_reason="cozify_unavailable",
        )


class PriceUnavailableFallbackService:
    def execute(self):
        return HeatingControlResult(
            is_summer=False,
            price=None,
            indoor_temperature=None,
            outdoor_temperature=5.0,
            target_temperature=20.0,
            fallback_used=True,
            fallback_reason="price_data_unavailable",
        )


class FailingService:
    def execute(self):
        raise ApplicationError("boom")


def _set_required_env(monkeypatch) -> None:
    monkeypatch.setenv("THERMIA_USERNAME_PARAMETER", "/lambda/thermia/username")
    monkeypatch.setenv("THERMIA_PASSWORD_PARAMETER", "/lambda/thermia/secret")
    monkeypatch.setenv("COZIFY_CONFIG_PARAMETER", "/lambda/cozify/config")
    monkeypatch.setenv("S3_BUCKET", "spot-electricity-prices-149796722280-eu-west-1-an")
    monkeypatch.setenv("S3_PRICE_KEY", "latest-prices.json")
    monkeypatch.setenv("S3_HEATING_HISTORY_KEY", "heating-history.json")
    monkeypatch.setenv("S3_LEGIONELLA_BOOST_KEY", "latest-legionella-boost-time.json")
    monkeypatch.setenv("NOMINAL_TARGET_TEMPERATURE", "20.0")
    monkeypatch.setenv("NOMINAL_INDOOR_TEMPERATURE", "21.0")
    monkeypatch.setenv("MIN_TARGET_TEMPERATURE", "17.0")
    monkeypatch.setenv("MAX_TARGET_TEMPERATURE", "21.0")
    monkeypatch.setenv("REFERENCE_PRICE", "5.0")
    monkeypatch.setenv("LOW_TEMPERATURE_PROTECTION_MARGIN", "2.0")
    monkeypatch.setenv("PRICE_GAIN", "1.2")
    monkeypatch.setenv("INDOOR_TEMPERATURE_GAIN", "1.5")
    monkeypatch.setenv("LOW_TEMPERATURE_BOOST", "3.0")
    monkeypatch.setenv("DEFAULT_HEATING_CURVE", "36")
    monkeypatch.setenv("SHUTDOWN_OUTDOOR_TEMPERATURE_LIMIT", "-5.0")
    monkeypatch.setenv("SHUTDOWN_SUPPLY_LINE_TEMPERATURE_LIMIT", "25")
    monkeypatch.setenv("SUMMER_MODE_AVERAGE_TEMPERATURE_THRESHOLD", "15.0")
    monkeypatch.setenv("SUMMER_MODE_MINIMUM_TEMPERATURE_THRESHOLD", "10.0")
    monkeypatch.setenv("IDLE_TARGET_TEMPERATURE", "10")
    monkeypatch.setenv("MIN_RUN", "2")
    monkeypatch.setenv("MIN_IDLE", "2")
    monkeypatch.setenv("HAPPY_PRICE_BIAS", "0.0")
    monkeypatch.setenv("LEGIONELLA_DISINFECTION_TEMPERATURE", "60")
    monkeypatch.setenv("TIMEZONE", "Europe/Helsinki")
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("THERMIA_DEMO_MODE", "false")


def test_lambda_handler_success(monkeypatch) -> None:
    _set_required_env(monkeypatch)
    monkeypatch.setattr(handler_optimizer, "create_heating_control_service", lambda settings: DummyService())

    response = handler_optimizer.lambda_handler({}, DummyContext())

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["requestId"] == "req-123"
    assert body["priceSntPerKwh"] == 2.5
    assert body["indoorTemperatureC"] == 20.7
    assert body["targetTemperatureC"] == 20.3
    assert body["fallbackUsed"] is False


def test_lambda_handler_returns_500_on_application_error(monkeypatch) -> None:
    _set_required_env(monkeypatch)
    monkeypatch.setattr(
        handler_optimizer, "create_heating_control_service", lambda settings: FailingService()
    )

    response = handler_optimizer.lambda_handler({}, DummyContext())

    assert response["statusCode"] == 500
    body = json.loads(response["body"])
    assert body["requestId"] == "req-123"
    assert "Failed to control" in body["message"]


def test_lambda_handler_emits_metric_for_cozify_unavailable_fallback(monkeypatch) -> None:
    _set_required_env(monkeypatch)
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "thermia-optimize-heating")
    monkeypatch.setattr(
        handler_optimizer,
        "create_heating_control_service",
        lambda settings: CozifyUnavailableFallbackService(),
    )

    class FakeCloudWatchClient:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def put_metric_data(self, Namespace: str, MetricData: list[dict]) -> None:
            self.calls.append({"Namespace": Namespace, "MetricData": MetricData})

    class FakeLambdaClient:
        def invoke(self, FunctionName: str, InvocationType: str, Payload: str) -> dict[str, int]:
            assert FunctionName == "ingest-spot-prices"
            assert InvocationType == "Event"
            _ = Payload
            return {"StatusCode": 202}

    fake_cloudwatch = FakeCloudWatchClient()

    def fake_boto3_client(service_name: str, region_name: str):
        assert region_name == "eu-west-1"
        if service_name == "cloudwatch":
            return fake_cloudwatch
        if service_name == "lambda":
            return FakeLambdaClient()
        assert region_name == "eu-west-1"
        raise AssertionError(service_name)

    monkeypatch.setattr(handler_optimizer.boto3, "client", fake_boto3_client)

    response = handler_optimizer.lambda_handler({}, DummyContext())

    assert response["statusCode"] == 200
    assert len(fake_cloudwatch.calls) == 1
    call = fake_cloudwatch.calls[0]
    assert call["Namespace"] == handler_optimizer.FALLBACK_METRIC_NAMESPACE
    assert call["MetricData"][0]["MetricName"] == handler_optimizer.ERROR_METRIC_NAME
    assert call["MetricData"][0]["Dimensions"] == [
        {"Name": "FunctionName", "Value": "thermia-optimize-heating"},
    ]
    assert call["MetricData"][0]["Value"] == 1.0


def test_lambda_handler_does_not_emit_metric_when_no_fallback(monkeypatch) -> None:
    _set_required_env(monkeypatch)
    monkeypatch.setattr(handler_optimizer, "create_heating_control_service", lambda settings: DummyService())

    class FakeCloudWatchClient:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def put_metric_data(self, Namespace: str, MetricData: list[dict]) -> None:
            self.calls.append({"Namespace": Namespace, "MetricData": MetricData})

    fake_cloudwatch = FakeCloudWatchClient()
    monkeypatch.setattr(handler_optimizer.boto3, "client", lambda *args, **kwargs: fake_cloudwatch)

    response = handler_optimizer.lambda_handler({}, DummyContext())

    assert response["statusCode"] == 200
    assert fake_cloudwatch.calls == []


def test_lambda_handler_emits_metric_for_price_unavailable_fallback(monkeypatch) -> None:
    _set_required_env(monkeypatch)
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "thermia-optimize-heating")
    monkeypatch.setattr(
        handler_optimizer,
        "create_heating_control_service",
        lambda settings: PriceUnavailableFallbackService(),
    )

    class FakeCloudWatchClient:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def put_metric_data(self, Namespace: str, MetricData: list[dict]) -> None:
            self.calls.append({"Namespace": Namespace, "MetricData": MetricData})

    fake_cloudwatch = FakeCloudWatchClient()

    def fake_boto3_client(service_name: str, region_name: str):
        assert region_name == "eu-west-1"
        if service_name == "cloudwatch":
            return fake_cloudwatch
        if service_name == "lambda":
            return FakeLambdaClient()
        raise AssertionError(service_name)

    monkeypatch.setattr(handler_optimizer.boto3, "client", fake_boto3_client)

    response = handler_optimizer.lambda_handler({}, DummyContext())

    assert response["statusCode"] == 200
    assert len(fake_cloudwatch.calls) == 1
    call = fake_cloudwatch.calls[0]
    assert call["Namespace"] == handler_optimizer.FALLBACK_METRIC_NAMESPACE
    assert call["MetricData"][0]["MetricName"] == handler_optimizer.ERROR_METRIC_NAME
    assert call["MetricData"][0]["Dimensions"] == [
        {"Name": "FunctionName", "Value": "thermia-optimize-heating"},
    ]
    assert call["MetricData"][0]["Value"] == 1.0


def test_lambda_handler_emits_failure_metric_on_application_error(monkeypatch) -> None:
    _set_required_env(monkeypatch)
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "thermia-optimize-heating")
    monkeypatch.setattr(
        handler_optimizer,
        "create_heating_control_service",
        lambda settings: FailingService(),
    )

    class FakeCloudWatchClient:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def put_metric_data(self, Namespace: str, MetricData: list[dict]) -> None:
            self.calls.append({"Namespace": Namespace, "MetricData": MetricData})

    fake_cloudwatch = FakeCloudWatchClient()

    def fake_boto3_client(service_name: str, region_name: str):
        assert service_name == "cloudwatch"
        assert region_name == "eu-west-1"
        return fake_cloudwatch

    monkeypatch.setattr(handler_optimizer.boto3, "client", fake_boto3_client)

    response = handler_optimizer.lambda_handler({}, DummyContext())

    assert response["statusCode"] == 500
    assert len(fake_cloudwatch.calls) == 1
    call = fake_cloudwatch.calls[0]
    assert call["Namespace"] == handler_optimizer.FALLBACK_METRIC_NAMESPACE
    assert call["MetricData"][0]["MetricName"] == handler_optimizer.ERROR_METRIC_NAME
    assert call["MetricData"][0]["Dimensions"] == [
        {"Name": "FunctionName", "Value": "thermia-optimize-heating"},
    ]
    assert call["MetricData"][0]["Value"] == 1.0
