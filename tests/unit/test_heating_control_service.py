import random
from datetime import UTC, datetime, timedelta

from adapters.thermia_client import OperationMode
from application.heating_control_service import HeatingControlService
from config.settings import OptimizerSettings


class FakeHeatPump:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def set_temperature(self, target_temperature: int) -> None:
        self.calls.append(target_temperature)


class FakeParameterStoreClient:
    def __init__(self) -> None:
        self.values = {
            "/lambda/thermia/username": "user",
            "/lambda/thermia/secret": "pass",
            "/lambda/cozify/config": (
                '{"version": 1, "cloud_token": "test", "hub_id": "h", '
                '"hub_name": "h", "email": "test@example.com", '
                '"temperature_sensor_id": "s"}'
            ),
        }

    def get_secure_parameter(self, parameter_name: str) -> str:
        return self.values[parameter_name]


class FakeThermiaClient:
    def __init__(self, username: str, password: str) -> None:
        _ = username
        _ = password
        self.last_target = None
        self._heat_pump = FakeHeatPump()

    def get_operation_mode(self) -> OperationMode:
        return OperationMode.AUTO

    def set_operation_mode(self, mode) -> None:
        _ = mode

    def set_target_temperature(self, target_temperature: int) -> None:
        self.last_target = target_temperature

    def set_heating_curve(self, target_curve: int) -> None:
        _ = target_curve

    def update_data(self) -> None:
        pass

    def get_heating_curve(self) -> int:
        return 0

    def is_heating(self) -> bool:
        return False

    def is_hot_water(self) -> bool:
        return False

    def is_brine_pump(self) -> bool:
        return False

    def get_supply_line_temperature(self) -> int:
        return 0

    def get_desired_indoor_temperature(self) -> int:
        return 0

    def get_outdoor_temperature(self) -> int:
        return 0

    def get_integral(self) -> int:
        return 0

    def get_running_operational_statuses(self) -> str:
        return ""

    def get_hot_water_temperature(self) -> int:
        return 50

    def get_24h_historical_outdoor_temperatures(self) -> list[int]:
        return [0] * 96


class FakeS3Client:
    def __init__(
        self, price: float | None, should_fail: bool = False, initial_history: list | None = None
    ) -> None:
        self.price = price
        self.should_fail = should_fail
        self.initial_history = initial_history
        self.writes: list[tuple[str, str, dict]] = []
        self.writes: list[tuple[str, str, dict]] = []

    def _iso_z(self, dt):
        return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def _generate_prices_data(
        self,
        slots_before=2,
        slots_after=2,
        base_price=2.5,
        price_jitter=0.15,
    ):
        now = datetime.now(UTC)

        # Floor now to the start of the current 15‑minute slot
        slot_start = now.replace(
            minute=(now.minute // 15) * 15,
            second=0,
            microsecond=0,
        )

        prices = []

        for i in range(-slots_before, slots_after + 1):
            start = slot_start + timedelta(minutes=15 * i)
            end = start + timedelta(minutes=15, milliseconds=-1)

            prices.append(
                {
                    "price": round(
                        base_price + random.uniform(-price_jitter, price_jitter),
                        3,
                    ),
                    "startDate": self._iso_z(start),
                    "endDate": self._iso_z(end),
                }
            )

        return {"prices": prices}

    # def get_current_price(self, bucket: str, key: str) -> float:
    #     _ = bucket
    #     _ = key
    #     if self.should_fail:
    #         from application.errors import S3DataRetrievalError

    #         raise S3DataRetrievalError("s3 failed")
    #     assert self.price is not None
    #     return self.price

    def read_json(self, bucket: str, key: str) -> dict:
        _ = bucket
        if self.should_fail:
            from application.errors import S3DataRetrievalError

            raise S3DataRetrievalError("s3 failed")

        # If caller requests heating history, return the provided initial history
        if key == "heating-history.json" or "heating-history" in key:
            return {"history": self.initial_history or []}

        # If caller requests legionella boost time, return a default timestamp
        if key == "latest-legionella-boost-time.json" or "legionella" in key:
            now = datetime.now(UTC)
            return {"latest_legionella_boost_time": self._iso_z(now)}

        return self._generate_prices_data()

    def write_json(self, bucket: str, key: str, payload: dict) -> None:
        if self.should_fail:
            from application.errors import S3DataRetrievalError

            raise S3DataRetrievalError("s3 failed")
        self.writes.append((bucket, key, payload))

    # def get_heating_history(self, bucket: str, key: str) -> dict:
    #     _ = bucket
    #     _ = key
    #     if self.should_fail:
    #         from application.errors import S3DataRetrievalError

    #         raise S3DataRetrievalError("s3 failed")
    #     return {"history": []}


class FakeCozifyClient:
    def __init__(self, temperature: float, should_fail: bool = False) -> None:
        self.temperature = temperature
        self.should_fail = should_fail
        self.sensor_id = "sensor-from-config"
        self.last_sensor_id: str | None = None

    def get_configured_temperature_sensor_id(self) -> str:
        return self.sensor_id

    def get_room_temperature(self, sensor_id: str) -> float:
        self.last_sensor_id = sensor_id
        if self.should_fail:
            from application.errors import CozifyDataError

            raise CozifyDataError("cozify failed")
        return self.temperature


def _settings() -> OptimizerSettings:
    return OptimizerSettings(
        thermia_username_parameter="/lambda/thermia/username",
        thermia_password_parameter="/lambda/thermia/secret",
        cozify_config_parameter="/lambda/cozify/config",
        s3_bucket="spot-electricity-prices-149796722280-eu-west-1-an",
        s3_price_key="latest-prices.json",
        s3_heating_history_key="heating-history.json",
        s3_legionella_boost_key="latest-legionella-boost-time.json",
        nominal_target_temperature=20.0,
        nominal_indoor_temperature=21.0,
        min_target_temperature=17.0,
        max_target_temperature=21.0,
        reference_price=5.0,
        low_temperature_protection_margin=2.0,
        price_gain=1.2,
        indoor_temperature_gain=1.5,
        low_temperature_boost=3.0,
        default_heating_curve=36,
        aws_region="eu-west-1",
        timezone="Europe/Helsinki",
        log_level="INFO",
        thermia_demo_mode=False,
        shutdown_outdoor_temperature_limit=-5.0,
        shutdown_supply_line_temperature_limit=27,
        summer_mode_average_temperature_threshold=15.0,
        summer_mode_minimum_temperature_threshold=10.0,
        idle_target_temperature=10,
        min_run=2,
        min_idle=2,
        happy_price_bias=0.0,
        legionella_disinfection_temperature=60,
    )


def test_execute_success_path_computes_non_fallback_target() -> None:
    thermia_client = FakeThermiaClient("user", "pass")
    cozify_client = FakeCozifyClient(temperature=20.0)
    service = HeatingControlService(
        settings=_settings(),
        s3_client=FakeS3Client(price=3.0),
        thermia_client=thermia_client,
        cozify_client=cozify_client,
    )

    result = service.execute()

    assert result.fallback_used is False


def test_execute_uses_tnom_fallback_when_price_unavailable() -> None:
    thermia_client = FakeThermiaClient("user", "pass")
    service = HeatingControlService(
        settings=_settings(),
        s3_client=FakeS3Client(price=None, should_fail=True),
        thermia_client=thermia_client,
        cozify_client=FakeCozifyClient(temperature=20.0),
    )

    result = service.execute()

    assert result.fallback_used is True
    assert result.fallback_reason == "price_data_unavailable"


def test_execute_uses_tnom_fallback_when_cozify_unavailable() -> None:
    thermia_client = FakeThermiaClient("user", "pass")
    service = HeatingControlService(
        settings=_settings(),
        s3_client=FakeS3Client(price=2.5),
        thermia_client=thermia_client,
        cozify_client=FakeCozifyClient(temperature=20.0, should_fail=True),
    )

    result = service.execute()

    assert result.fallback_used is True
    assert result.fallback_reason == "cozify_unavailable"


def test_history_replace_and_prune_behavior() -> None:
    # Prepare deterministic slot start/end matching service logic
    now = datetime.now(UTC)
    slot_start = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
    slot_end = slot_start + timedelta(minutes=15) - timedelta(milliseconds=1)

    def iso_z(dt):
        return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    # Existing history contains an entry for the current slot (will be replaced)
    existing_entry = {
        "is_heating": False,
        "startDate": iso_z(slot_start),
        "endDate": iso_z(slot_end),
    }

    # Old entry beyond 12 hours should be pruned
    old_entry = {
        "is_heating": True,
        "startDate": iso_z(slot_start - timedelta(hours=13)),
        "endDate": iso_z(
            slot_start - timedelta(hours=13) + timedelta(minutes=15) - timedelta(milliseconds=1)
        ),
    }

    # Recent entry within 12 hours should be kept
    recent_entry = {
        "is_heating": False,
        "startDate": iso_z(slot_start - timedelta(hours=6)),
        "endDate": iso_z(
            slot_start - timedelta(hours=6) + timedelta(minutes=15) - timedelta(milliseconds=1)
        ),
    }

    fake_s3 = FakeS3Client(price=2.5, initial_history=[existing_entry, old_entry, recent_entry])

    thermia_client = FakeThermiaClient("user", "pass")
    # Force cozify failure so service marks is_heating_slot True (ensures replacement)
    cozify_client = FakeCozifyClient(temperature=20.0, should_fail=True)

    service = HeatingControlService(
        settings=_settings(),
        s3_client=fake_s3,
        thermia_client=thermia_client,
        cozify_client=cozify_client,
    )

    service.execute()

    # Verify S3 write occurred
    assert fake_s3.writes, "No writes recorded to S3"
    _, _, payload = fake_s3.writes[-1]
    hist = payload.get("history", [])

    # The old entry (13h) should be pruned
    starts = [e["startDate"] for e in hist]
    assert old_entry["startDate"] not in starts

    # Recent entry should be present
    assert recent_entry["startDate"] in starts

    # The existing entry should have been replaced by a new entry with same startDate
    # and since we forced cozify failure, is_heating should be True
    for e in hist:
        if e["startDate"] == existing_entry["startDate"]:
            assert e["is_heating"] is True
            break
    else:
        raise AssertionError("Replaced entry not found in history")
