from __future__ import annotations

from collections.abc import Mapping


class AppError(Exception):
    """Base class for all application errors."""

    status_code = 500
    code = "internal_error"

    def __init__(self, detail: str, *, details: Mapping[str, int] | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.details = dict(details) if details else None


class InvalidRequestError(AppError):
    """Client sent a malformed or invalid request (400)."""

    status_code = 400
    code = "invalid_request"


class SourceDurationUnknownError(InvalidRequestError):
    """A source is valid but its complete duration cannot be verified."""

    code = "source_duration_unknown"


class SourceTooLongError(InvalidRequestError):
    """A readable source exceeds Talven's supported duration ceiling."""

    code = "source_too_long"


class InsufficientVideoTimeError(InvalidRequestError):
    """A known source duration exceeds the account's spendable balance."""

    code = "insufficient_video_time"


class NoVideoTimeError(InvalidRequestError):
    """An account has no spendable video time."""

    code = "no_video_time"


class BalanceBlockedError(InvalidRequestError):
    """Outstanding usage debt currently blocks new briefing admission."""

    code = "balance_blocked"


class AuthenticationError(AppError):
    """Client is not authenticated or token is invalid/expired (401)."""

    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    """Client is authenticated but lacks permission to access the resource (403)."""

    status_code = 403
    code = "forbidden"


class ConflictError(AppError):
    """Request conflicts with the current resource state (409)."""

    status_code = 409
    code = "conflict"


class PublicBriefingAvailableError(ConflictError):
    """A free Listed briefing is available for the submitted source."""

    code = "public_briefing_available"


class ActiveJobLimitError(ConflictError):
    """The account already has the maximum number of billable jobs in progress."""

    code = "active_job_limit_reached"


class VideoTimeCommittedError(ConflictError):
    """Unsettled jobs leave too little spendable time for the requested source."""

    code = "video_time_committed"


class ActiveBriefingsRefundError(ConflictError):
    """A pack refund must wait for the account's active billable jobs."""

    code = "active_briefings_refund_blocked"


class NotFoundError(AppError):
    """Requested resource does not exist (404)."""

    status_code = 404
    code = "not_found"


class RateLimitError(AppError):
    """Client has exceeded rate limits (429)."""

    status_code = 429
    code = "rate_limit_exceeded"


class RequestTooLargeError(AppError):
    """Request body exceeds server limits (413)."""

    status_code = 413
    code = "request_too_large"


class ConfigurationError(AppError):
    """Server misconfiguration (500)."""

    status_code = 500
    code = "configuration_error"


class ExternalServiceError(AppError):
    """Upstream service failed or returned an invalid response (502)."""

    status_code = 502
    code = "external_service_error"


class UsageSettlementError(ExternalServiceError):
    """Post-processing usage accounting could not be finalized."""

    code = "usage_settlement_failed"


class NotReadyError(AppError):
    """Service is temporarily unavailable (503)."""

    status_code = 503
    code = "not_ready"
