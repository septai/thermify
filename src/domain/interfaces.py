from typing import Any, Protocol

from adapters.thermia_client import OperationMode
from domain.types import ElectricityPricePayload


class S3ClientProtocol(Protocol):
    """Interface for S3 operations needed by the service."""

    def read_json(self, bucket: str, key: str) -> Any:
        """Read and deserialize JSON payload from an S3 object."""
        ...

    def write_json(self, bucket: str, key: str, payload: Any) -> Any:
        """Serialize and write JSON payload to an S3 object."""
        ...


class CozifyClientProtocol(Protocol):
    """Interface for reading indoor temperature from Cozify."""

    def get_configured_temperature_sensor_id(self) -> str:
        """Return configured Cozify temperature sensor id."""
        ...

    def get_room_temperature(self, sensor_id: str) -> float:
        """Return indoor temperature in Celsius."""
        ...


class ParameterStoreClientProtocol(Protocol):
    """Interface for secure parameter retrieval."""

    def get_secure_parameter(self, parameter_name: str) -> str:
        """Return decrypted value for the given parameter name."""
        ...

    def put_cozify_config_json(self, parameter_name: str, config_dict: dict[str, Any]) -> None:
        """Write updated Cozify configuration to SSM Parameter Store as JSON."""
        ...


class ElectricityPriceClientProtocol(Protocol):
    """Interface for fetching electricity price data."""

    def fetch_latest_prices(self) -> ElectricityPricePayload:
        """Fetch latest electricity price data and return as a dictionary."""
        ...

class ThermiaClientProtocol(Protocol):
    """Interface for Thermia operations used by the service."""

    def update_data(self) -> None:
        """Update heat pump data."""
        ...

    def get_operation_mode(self) -> OperationMode:
        """Return current operation mode."""
        ...

    def set_operation_mode(self, mode: OperationMode) -> None:
        """Set operation mode for heat pump."""
        ...

    def set_target_temperature(self, target_temperature: int) -> None:
        """Set target temperature for heat pump."""
        ...

    def get_heating_curve(self) -> int:
        """Return heating curve."""
        ...

    def set_heating_curve(self, target_curve: int) -> None:
        """Set heating curve."""
        ...

    def is_heating(self) -> bool:
        """Return True if heat pump is currently heating."""
        ...

    def is_hot_water(self) -> bool:
        """Return True if heat pump is currently producing hot water."""
        ...

    def is_brine_pump(self) -> bool:
        """Return True if brine pump is currently running."""
        ...

    def get_supply_line_temperature(self) -> int:
        """Return supply line temperature."""
        ...

    def get_desired_indoor_temperature(self) -> int:
        """Return desired indoor temperature setting."""
        ...

    def get_outdoor_temperature(self) -> int:
        """Return current outdoor temperature."""
        ...

    def get_integral(self) -> int:
        """Return operational status integral."""
        ...

    def get_running_operational_statuses(self) -> str:
        """Return running operational statuses."""
        ...

    def get_hot_water_temperature(self) -> int:
        """Return hot water temperature."""
        ...

    def get_24h_historical_outdoor_temperatures(self) -> list[int]:
        """Return list of outdoor temperatures for the last 24 hours."""
        ...