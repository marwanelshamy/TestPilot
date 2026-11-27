"""Application errors. Each maps to the shared error body {error: {code, message, details, correlationId}} (M2 §4.5)."""

from typing import Any


class AppError(Exception):
    status_code = 500
    code = "INTERNAL_ERROR"

    def __init__(self, message: str, details: dict[str, Any] | None = None, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        if code:
            self.code = code


class ValidationFailed(AppError):
    status_code = 400
    code = "VALIDATION_ERROR"


class Unauthorized(AppError):
    status_code = 401
    code = "AUTH_REQUIRED"


class Forbidden(AppError):
    status_code = 403
    code = "FORBIDDEN"


class NotFound(AppError):
    status_code = 404
    code = "NOT_FOUND"


class Conflict(AppError):
    """code is one of TEST_NOT_APPROVED, VERSION_CONFLICT, INVALID_STATE."""

    status_code = 409
    code = "INVALID_STATE"


class AiUnavailable(AppError):
    status_code = 503
    code = "AI_UNAVAILABLE"


class QueueUnavailable(AppError):
    status_code = 503
    code = "QUEUE_UNAVAILABLE"
