"""Heartbeat watchdog loop (tactic T1). Runs in a daemon thread inside the Core Backend process and
calls ExecutionOrchestrator.sweep() every heartbeat interval with a fresh session."""

import logging
import threading

from app.core.config import Settings
from app.core.database import session_factory
from app.integration.job_publisher import JobPublisher

log = logging.getLogger(__name__)


class Watchdog:
    def __init__(self, settings: Settings, publisher: JobPublisher):
        self.settings = settings
        self.publisher = publisher
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="execution-watchdog", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        from app.services.orchestrator import ExecutionOrchestrator  # avoid import cycle at module load

        while not self._stop.wait(self.settings.heartbeat_interval_seconds):
            session = session_factory()()
            try:
                for ex_id, reason in ExecutionOrchestrator(session, self.publisher, self.settings).sweep():
                    log.warning("watchdog interrupted execution %s: %s", ex_id, reason.value)
            except Exception:  # keep the loop alive; next tick retries
                session.rollback()
                log.exception("watchdog sweep failed")
            finally:
                session.close()
