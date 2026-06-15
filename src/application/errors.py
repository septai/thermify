"""Custom exception types used by the application layer."""


class ApplicationError(Exception):
    """Base exception for controlled application failures."""


class CredentialsRetrievalError(ApplicationError):
    """Raised when secure credentials cannot be loaded."""


class ThermiaAuthenticationError(ApplicationError):
    """Raised when login to Thermia API fails."""


class ThermiaApiError(ApplicationError):
    """Raised when Thermia API operations fail unexpectedly."""


class NoHeatPumpsError(ApplicationError):
    """Raised when no Thermia devices are available for the account."""


class S3DataRetrievalError(ApplicationError):
    """Raised when JSON data cannot be read from or written to S3."""


class S3DataValidationError(ApplicationError):
    """Raised when S3 JSON payload is invalid or cannot be serialized."""


class CozifyAuthenticationError(ApplicationError):
    """Raised when authentication to Cozify API fails."""


class CozifyDataError(ApplicationError):
    """Raised when required Cozify data cannot be retrieved or parsed."""

class ExternalApiError(ApplicationError):
    """Raised when an external API request fails."""

class InvalidApiResponseError(ApplicationError):
    """Raised when an external API returns an unexpected response format."""