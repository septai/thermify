"""Environment-backed configuration for Lambda runtime."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class IngestorSettings:
    """Runtime settings for the price ingestor Lambda, loaded from environment variables."""

    power_price_api_url: str
    s3_bucket: str
    s3_price_key: str
    aws_region: str
    log_level: str

    @classmethod
    def from_env(cls) -> IngestorSettings:
        """Build ingestor settings from process environment."""
        power_price_api_url = os.getenv("POWER_PRICE_API_URL")
        s3_bucket = os.getenv("S3_BUCKET")
        s3_price_key = os.getenv("S3_PRICE_KEY")
        aws_region = os.getenv("AWS_REGION")
        log_level = os.getenv("LOG_LEVEL")

        if not power_price_api_url:
            raise ValueError("Missing required environment variable POWER_PRICE_API_URL")
        if not s3_bucket:
            raise ValueError("Missing required environment variable S3_BUCKET")
        if not s3_price_key:
            raise ValueError("Missing required environment variable S3_PRICE_KEY")
        if not aws_region:
            raise ValueError("Missing required environment variable AWS_REGION")
        if not log_level:
            raise ValueError("Missing required environment variable LOG_LEVEL")

        return cls(
            power_price_api_url=power_price_api_url,
            s3_bucket=s3_bucket,
            s3_price_key=s3_price_key,
            aws_region=aws_region,
            log_level=log_level,
        )
        


@dataclass(frozen=True)
class OptimizerSettings:
    """Runtime settings loaded from Lambda environment variables."""

    thermia_username_parameter: str
    thermia_password_parameter: str
    cozify_config_parameter: str
    s3_bucket: str
    s3_price_key: str
    s3_heating_history_key: str
    s3_legionella_boost_key: str
    nominal_target_temperature: float
    nominal_indoor_temperature: float
    min_target_temperature: float
    max_target_temperature: float
    reference_price: float
    low_temperature_protection_margin: float
    price_gain: float
    indoor_temperature_gain: float
    low_temperature_boost: float
    default_heating_curve: int
    aws_region: str
    timezone: str
    log_level: str
    thermia_demo_mode: bool
    shutdown_outdoor_temperature_limit: float
    shutdown_supply_line_temperature_limit: int
    summer_mode_average_temperature_threshold: float
    summer_mode_minimum_temperature_threshold: float
    idle_target_temperature: int
    min_run: int
    min_idle: int
    happy_price_bias: float
    legionella_disinfection_temperature: int

    @classmethod
    def from_env(cls) -> OptimizerSettings:
        """Build settings from process environment and validate required values."""
        username_param = os.getenv("THERMIA_USERNAME_PARAMETER")
        password_param = os.getenv("THERMIA_PASSWORD_PARAMETER")
        cozify_config_parameter = os.getenv("COZIFY_CONFIG_PARAMETER")
        s3_bucket = os.getenv("S3_BUCKET")
        s3_price_key = os.getenv("S3_PRICE_KEY")
        s3_heating_history_key = os.getenv("S3_HEATING_HISTORY_KEY")
        s3_legionella_boost_key = os.getenv("S3_LEGIONELLA_BOOST_KEY")
        nominal_target_temperature = os.getenv("NOMINAL_TARGET_TEMPERATURE")
        nominal_indoor_temperature = os.getenv("NOMINAL_INDOOR_TEMPERATURE")
        min_target_temperature = os.getenv("MIN_TARGET_TEMPERATURE")
        max_target_temperature = os.getenv("MAX_TARGET_TEMPERATURE")
        reference_price = os.getenv("REFERENCE_PRICE")
        low_temperature_protection_margin = os.getenv("LOW_TEMPERATURE_PROTECTION_MARGIN")
        price_gain = os.getenv("PRICE_GAIN")
        indoor_temperature_gain = os.getenv("INDOOR_TEMPERATURE_GAIN")
        low_temperature_boost = os.getenv("LOW_TEMPERATURE_BOOST")
        default_heating_curve = os.getenv("DEFAULT_HEATING_CURVE")
        aws_region = os.getenv("AWS_REGION")
        timezone = os.getenv("TIMEZONE")
        log_level = os.getenv("LOG_LEVEL")
        thermia_demo_mode = os.getenv("THERMIA_DEMO_MODE")
        shutdown_outdoor_temperature_limit = os.getenv("SHUTDOWN_OUTDOOR_TEMPERATURE_LIMIT")
        shutdown_supply_line_temperature_limit = os.getenv("SHUTDOWN_SUPPLY_LINE_TEMPERATURE_LIMIT")
        summer_mode_average_temperature_threshold = os.getenv(
            "SUMMER_MODE_AVERAGE_TEMPERATURE_THRESHOLD"
        )
        summer_mode_minimum_temperature_threshold = os.getenv(
            "SUMMER_MODE_MINIMUM_TEMPERATURE_THRESHOLD"
        )
        idle_target_temperature = os.getenv("IDLE_TARGET_TEMPERATURE")
        min_run = os.getenv("MIN_RUN")
        min_idle = os.getenv("MIN_IDLE")
        happy_price_bias = os.getenv("HAPPY_PRICE_BIAS")
        legionella_disinfection_temperature = os.getenv(
            "LEGIONELLA_DISINFECTION_TEMPERATURE"
        )

        if not username_param:
            raise ValueError("Missing required environment variable THERMIA_USERNAME_PARAMETER")
        if not password_param:
            raise ValueError("Missing required environment variable THERMIA_PASSWORD_PARAMETER")
        if not cozify_config_parameter:
            raise ValueError("Missing required environment variable COZIFY_CONFIG_PARAMETER")
        if not s3_bucket:
            raise ValueError("Missing required environment variable S3_BUCKET")
        if not s3_price_key:
            raise ValueError("Missing required environment variable S3_PRICE_KEY")
        if not s3_heating_history_key:
            raise ValueError("Missing required environment variable S3_HEATING_HISTORY_KEY")
        if not s3_legionella_boost_key:
            raise ValueError("Missing required environment variable S3_LEGIONELLA_BOOST_KEY")
        if not nominal_target_temperature:
            raise ValueError("Missing required environment variable NOMINAL_TARGET_TEMPERATURE")
        if not nominal_indoor_temperature:
            raise ValueError("Missing required environment variable NOMINAL_INDOOR_TEMPERATURE")
        if not min_target_temperature:
            raise ValueError("Missing required environment variable MIN_TARGET_TEMPERATURE")
        if not max_target_temperature:
            raise ValueError("Missing required environment variable MAX_TARGET_TEMPERATURE")
        if not reference_price:
            raise ValueError("Missing required environment variable REFERENCE_PRICE")
        if not low_temperature_protection_margin:
            raise ValueError(
                "Missing required environment variable LOW_TEMPERATURE_PROTECTION_MARGIN"
            )
        if not price_gain:
            raise ValueError("Missing required environment variable PRICE_GAIN")
        if not indoor_temperature_gain:
            raise ValueError("Missing required environment variable INDOOR_TEMPERATURE_GAIN")
        if not low_temperature_boost:
            raise ValueError("Missing required environment variable LOW_TEMPERATURE_BOOST")
        if not default_heating_curve:
            raise ValueError("Missing required environment variable DEFAULT_HEATING_CURVE")
        if not aws_region:
            raise ValueError("Missing required environment variable AWS_REGION")
        if not timezone:
            raise ValueError("Missing required environment variable TIMEZONE")
        if not log_level:
            raise ValueError("Missing required environment variable LOG_LEVEL")
        if not thermia_demo_mode:
            raise ValueError("Missing required environment variable THERMIA_DEMO_MODE")
        if not shutdown_outdoor_temperature_limit:
            raise ValueError(
                "Missing required environment variable SHUTDOWN_OUTDOOR_TEMPERATURE_LIMIT"
            )
        if not shutdown_supply_line_temperature_limit:
            raise ValueError(
                "Missing required environment variable SHUTDOWN_SUPPLY_LINE_TEMPERATURE_LIMIT"
            )
        if not summer_mode_average_temperature_threshold:
            raise ValueError(
                "Missing required environment variable SUMMER_MODE_AVERAGE_TEMPERATURE_THRESHOLD"
            )
        if not summer_mode_minimum_temperature_threshold:
            raise ValueError(
                "Missing required environment variable SUMMER_MODE_MINIMUM_TEMPERATURE_THRESHOLD"
            )
        if not idle_target_temperature:
            raise ValueError("Missing required environment variable IDLE_TARGET_TEMPERATURE")
        if not min_run:
            raise ValueError("Missing required environment variable MIN_RUN")
        if not min_idle:
            raise ValueError("Missing required environment variable MIN_IDLE")
        if happy_price_bias is None:
            raise ValueError("Missing required environment variable HAPPY_PRICE_BIAS")
        if not legionella_disinfection_temperature:
            raise ValueError(
                "Missing required environment variable"
                "LEGIONELLA_DISINFECTION_TEMPERATURE"
            )

        return cls(
            thermia_username_parameter=username_param,
            thermia_password_parameter=password_param,
            cozify_config_parameter=cozify_config_parameter,
            s3_bucket=s3_bucket,
            s3_price_key=s3_price_key,
            s3_heating_history_key=s3_heating_history_key,
            s3_legionella_boost_key=s3_legionella_boost_key,
            nominal_target_temperature=float(nominal_target_temperature),
            nominal_indoor_temperature=float(nominal_indoor_temperature),
            min_target_temperature=float(min_target_temperature),
            max_target_temperature=float(max_target_temperature),
            reference_price=float(reference_price),
            low_temperature_protection_margin=float(low_temperature_protection_margin),
            price_gain=float(price_gain),
            indoor_temperature_gain=float(indoor_temperature_gain),
            low_temperature_boost=float(low_temperature_boost),
            default_heating_curve=int(default_heating_curve),
            aws_region=aws_region,
            timezone=timezone,
            log_level=log_level,
            thermia_demo_mode=_parse_bool_env("THERMIA_DEMO_MODE", thermia_demo_mode),
            shutdown_outdoor_temperature_limit=float(shutdown_outdoor_temperature_limit),
            shutdown_supply_line_temperature_limit=int(shutdown_supply_line_temperature_limit),
            summer_mode_average_temperature_threshold=float(
                summer_mode_average_temperature_threshold
            ),
            summer_mode_minimum_temperature_threshold=float(
                summer_mode_minimum_temperature_threshold
            ),
            idle_target_temperature=int(idle_target_temperature),
            min_run=int(min_run),
            min_idle=int(min_idle),
            happy_price_bias=float(happy_price_bias),
            legionella_disinfection_temperature=int(legionella_disinfection_temperature),
        )


def _parse_bool_env(name: str, value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Environment variable {name} must be a boolean-like value (true/false)")
