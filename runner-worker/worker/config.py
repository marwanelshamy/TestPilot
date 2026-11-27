"""Worker settings from environment variables (T24). No database settings exist here on purpose:
the Runner Worker has no path to the database (ASR-1, ASR-3)."""

import os
import socket
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class WorkerSettings:
    amqp_url: str = field(default_factory=lambda: _env("AMQP_URL", "amqp://guest:guest@localhost:5672/"))
    sandbox_image: str = field(default_factory=lambda: _env("SANDBOX_IMAGE", "testpilot-sandbox:latest"))
    heartbeat_interval_seconds: float = field(default_factory=lambda: float(_env("HEARTBEAT_INTERVAL_SECONDS", "5")))
    worker_id: str = field(default_factory=lambda: _env("WORKER_ID", socket.gethostname())[:64])
    sandbox_pids_limit: int = field(default_factory=lambda: int(_env("SANDBOX_PIDS_LIMIT", "128")))
    sandbox_tmpfs_mb: int = field(default_factory=lambda: int(_env("SANDBOX_TMPFS_MB", "64")))
    # extra seconds the worker allows Docker to report back before treating the run as timed out
    kill_grace_seconds: float = field(default_factory=lambda: float(_env("KILL_GRACE_SECONDS", "2")))
