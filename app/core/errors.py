class AppError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class InvalidRequestError(AppError):
    status_code = 400
    code = "invalid_request"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ExternalServiceError(AppError):
    status_code = 502
    code = "external_service_error"
