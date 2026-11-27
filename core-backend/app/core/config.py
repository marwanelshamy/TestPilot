"""Settings from environment variables / .env (tactic T24: defer binding, no secrets in code)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./testpilot-dev.db"
    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_timeout_seconds: float = 10.0
    # Admission control (QAS-1 finding): keep below the API thread pool (40) and the DB pool (pool + overflow)
    max_inflight_requests: int = 25
    admission_wait_seconds: float = 5.0
    jwt_secret: str = "dev-only-secret-change-me-0123456789abcdef"
    jwt_expires_minutes: int = 60

    # AI Service Client (P9, T1, T3) — starting values, tuned in Phase 3
    ai_service_url: str = "http://ai-service:8001"
    ai_client_timeout_seconds: float = 10.0
    ai_client_retries: int = 2
    ai_breaker_failure_threshold: int = 5
    ai_breaker_reset_seconds: float = 30.0

    # Job publisher: "log" until Member 2 plugs in the AMQP publisher ("amqp")
    job_publisher: str = "log"
    amqp_url: str = "amqp://guest:guest@rabbitmq:5672/"

    # Execution limits (QAS-3) and watchdog (OI-007)
    run_time_limit_seconds: int = 30
    run_cpu: float = 1.0
    run_memory_mb: int = 256
    heartbeat_interval_seconds: int = 5
    watchdog_missed_heartbeats: int = 3
    watchdog_timeout_grace_seconds: int = 5
    watchdog_enabled: bool = True
    evidence_max_bytes: int = 65536

    seed_demo: bool = True
    demo_password: str = "TestPilot#2026"


@lru_cache
def get_settings() -> Settings:
    return Settings()
