class AppError(Exception):
    """Base class for all application errors."""

    status_code = 500
    code = "internal_error"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class InvalidRequestError(AppError):
    """Client sent a malformed or invalid request (400)."""

    status_code = 400
    code = "invalid_request"


class AuthenticationError(AppError):
    """Client is not authenticated or token is invalid/expired (401)."""

    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    """Client is authenticated but lacks permission to access the resource (403)."""

    status_code = 403
    code = "forbidden"


class NotFoundError(AppError):
    """Requested resource does not exist (404)."""

    status_code = 404
    code = "not_found"


class RateLimitError(AppError):
    """Client has exceeded rate limits (429)."""

    status_code = 429
    code = "rate_limit_exceeded"


class ConfigurationError(AppError):
    """Server misconfiguration (500)."""

    status_code = 500
    code = "configuration_error"


class ExternalServiceError(AppError):
    """Upstream service failed or returned an invalid response (502)."""

    status_code = 502
    code = "external_service_error"


class NotReadyError(AppError):
    """Service is temporarily unavailable (503)."""

    status_code = 503
    code = "not_ready"
