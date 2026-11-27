"""Core Backend entry point: `uvicorn --factory app.main:create_app` (routes under /api, forwarded by Nginx)."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.admission import AdmissionControl
from app.api.errors import install_error_handlers
from app.api.routers import auth, executions, projects, tests
from app.core.config import Settings, get_settings
from app.core.database import init_engine
from app.integration.ai_client import AiServiceClient, CircuitBreaker
from app.integration.job_publisher import JobPublisher, LogJobPublisher
from app.services.orchestrator.watchdog import Watchdog

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def build_publisher(settings: Settings) -> JobPublisher:
    if settings.job_publisher == "log":
        return LogJobPublisher()
    if settings.job_publisher == "amqp":
        from app.integration.amqp_publisher import AmqpJobPublisher

        return AmqpJobPublisher(settings.amqp_url)
    raise RuntimeError(f"Unknown JOB_PUBLISHER={settings.job_publisher!r} (supported: log, amqp)")


def create_app(
    settings: Settings | None = None,
    publisher: JobPublisher | None = None,
    ai_client: AiServiceClient | None = None,
    start_watchdog: bool | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    init_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
    )

    publisher = publisher or build_publisher(settings)
    ai_client = ai_client or AiServiceClient(
        settings.ai_service_url,
        settings.ai_client_timeout_seconds,
        settings.ai_client_retries,
        CircuitBreaker(settings.ai_breaker_failure_threshold, settings.ai_breaker_reset_seconds),
    )
    watchdog = Watchdog(settings, publisher)
    run_watchdog = settings.watchdog_enabled if start_watchdog is None else start_watchdog
    # Execution events come back over AMQP only when jobs go out over AMQP (Phase 4 wiring, link R8)
    listener = None
    if settings.job_publisher == "amqp":
        from app.api.listeners.execution_events import ExecutionEventListener

        listener = ExecutionEventListener(settings, publisher)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if run_watchdog:
            watchdog.start()
        if listener:
            listener.start()
        yield
        if listener:
            listener.stop()
        if run_watchdog:
            watchdog.stop()

    app = FastAPI(
        title="TestPilot AI — Core Backend",
        version="1.0.0",
        description="Public REST API (I1). Contract: docs/contracts/public-api.openapi.yaml",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.publisher = publisher
    app.state.ai_client = ai_client

    install_error_handlers(app)
    app.add_middleware(
        AdmissionControl, max_inflight=settings.max_inflight_requests, wait_seconds=settings.admission_wait_seconds
    )
    for r in (auth.router, projects.router, tests.router, executions.router):
        app.include_router(r, prefix="/api")

    @app.get("/api/health", tags=["health"])
    def health():
        return {"status": "ok", "aiCircuit": ai_client.breaker.state, "publisher": type(publisher).__name__}

    return app
