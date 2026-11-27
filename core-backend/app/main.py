"""Core Backend entry point: `uvicorn --factory app.main:create_app` (routes under /api, forwarded by Nginx)."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

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
    raise RuntimeError(
        f"JOB_PUBLISHER={settings.job_publisher!r} is not available yet "
        "(the AMQP adapter is added by the Runner/RabbitMQ owner in Phase 2/4)"
    )


def create_app(
    settings: Settings | None = None,
    publisher: JobPublisher | None = None,
    ai_client: AiServiceClient | None = None,
    start_watchdog: bool | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    init_engine(settings.database_url)

    publisher = publisher or build_publisher(settings)
    ai_client = ai_client or AiServiceClient(
        settings.ai_service_url,
        settings.ai_client_timeout_seconds,
        settings.ai_client_retries,
        CircuitBreaker(settings.ai_breaker_failure_threshold, settings.ai_breaker_reset_seconds),
    )
    watchdog = Watchdog(settings, publisher)
    run_watchdog = settings.watchdog_enabled if start_watchdog is None else start_watchdog

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if run_watchdog:
            watchdog.start()
        yield
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
    for r in (auth.router, projects.router, tests.router, executions.router):
        app.include_router(r, prefix="/api")

    @app.get("/api/health", tags=["health"])
    def health():
        return {"status": "ok", "aiCircuit": ai_client.breaker.state, "publisher": type(publisher).__name__}

    return app
