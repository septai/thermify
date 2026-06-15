from adapters.parameter_store import ParameterStoreClient
from application.errors import CredentialsRetrievalError


class FakeSsmClient:
    def get_parameter(self, Name: str, WithDecryption: bool) -> dict:
        assert WithDecryption is True
        return {"Parameter": {"Value": f"value-for-{Name}"}}


def test_parameter_store_reads_parameter_via_boto3() -> None:
    client = ParameterStoreClient(
        region_name="eu-west-1",
        ssm_client=FakeSsmClient(),
    )

    value = client.get_secure_parameter("/lambda/thermia/username")

    assert value == "value-for-/lambda/thermia/username"


def test_parameter_store_raises_when_boto3_call_fails() -> None:
    class BrokenSsmClient:
        def get_parameter(self, Name: str, WithDecryption: bool) -> dict:
            raise RuntimeError("ssm failed")

    client = ParameterStoreClient(
        region_name="eu-west-1",
        ssm_client=BrokenSsmClient(),
    )

    try:
        client.get_secure_parameter("/lambda/thermia/secret")
    except CredentialsRetrievalError as exc:
        assert "Failed to retrieve secure parameter" in str(exc)
    else:
        raise AssertionError("Expected CredentialsRetrievalError")


