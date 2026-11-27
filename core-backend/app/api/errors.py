"""Uniform error body (M2 §4.5): {"error": {code, message, details, correlationId}}."""

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import AppError

log = logging.getLogger(__name__)


def correlation_id(request: Request) -> str:
    return (
        getattr(request.state, "correlation_id", None)
        or request.headers.get("X-Correlation-ID")
        or uuid.uuid4().hex[:12]
    )


def _body(request: Request, status: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    cid = correlation_id(request)
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details or {}, "correlationId": cid}},
        headers={"X-Correlation-ID": cid},
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.middleware("http")
    async def add_correlation_id(request: Request, call_next):
        request.state.correlation_id = request.headers.get("X-Correlation-ID") or uuid.uuid4().hex[:12]
        response = await call_next(request)
        response.headers.setdefault("X-Correlation-ID", request.state.correlation_id)
        return response

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError):
        return _body(request, exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        fields = [{"field": ".".join(str(p) for p in e["loc"] if p != "body"), "error": e["msg"]} for e in exc.errors()]
        return _body(request, 400, "VALIDATION_ERROR", "Invalid request", {"fields": fields})

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        code = {404: "NOT_FOUND", 405: "VALIDATION_ERROR", 401: "AUTH_REQUIRED", 403: "FORBIDDEN"}.get(
            exc.status_code, "INTERNAL_ERROR"
        )
        return _body(request, exc.status_code, code, str(exc.detail))

    @app.exception_handler(PoolTimeoutError)
    async def busy(request: Request, exc: PoolTimeoutError):
        # load shedding: no DB connection free within DB_POOL_TIMEOUT_SECONDS -> clear, retryable 503
        log.warning("database pool exhausted [%s]", correlation_id(request))
        return _body(request, 503, "SERVICE_BUSY", "The service is busy. Please retry in a moment.")

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        log.exception("unhandled error [%s]", correlation_id(request))
        return _body(request, 500, "INTERNAL_ERROR", "Unexpected server error")
