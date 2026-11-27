"""Processes one ExecutionRequested job: heartbeats while the sandbox runs, then ExecutionFinished.

The worker reports RAW runner output only. It never decides PASSED/FAILED — that is the Execution
Orchestrator's job in the Core Backend (ASR-3, ADR-006).
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from worker.messages import (
    MAX_JUNIT_CHARS,
    MAX_STREAM_CHARS,
    ExecutionFinished,
    ExecutionHeartbeat,
    ExecutionRequested,
)
from worker.sandbox import Sandbox, SandboxResult

log = logging.getLogger(__name__)

Emit = Callable[[ExecutionHeartbeat | ExecutionFinished], Awaitable[None]]

TRUNC_MARKER = "\n...[truncated by runner]"


def cap(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[: limit - len(TRUNC_MARKER)] + TRUNC_MARKER, True


def build_finished(job: ExecutionRequested, r: SandboxResult, worker_id: str) -> ExecutionFinished:
    stdout, t1 = cap(r.stdout, MAX_STREAM_CHARS)
    stderr, t2 = cap(r.stderr, MAX_STREAM_CHARS)
    junit, detail = r.junit_xml, r.error_detail
    if junit is not None and len(junit) > MAX_JUNIT_CHARS:
        # a cut XML is not a report; send none so the orchestrator records INVALID_REPORT
        junit, detail = None, f"JUnit report too large ({len(r.junit_xml)} chars)"
    return ExecutionFinished(
        executionId=job.executionId,
        workerId=worker_id,
        outcome=r.outcome,
        exitCode=r.exit_code,
        junitXml=junit,
        stdout=stdout,
        stderr=stderr,
        truncated=t1 or t2,
        errorDetail=(detail or None) and detail[:2000],
        durationMs=max(0, r.duration_ms),
    )


class JobProcessor:
    def __init__(self, sandbox: Sandbox, worker_id: str, heartbeat_interval: float):
        self.sandbox = sandbox
        self.worker_id = worker_id
        self.interval = heartbeat_interval

    def _heartbeat(self, job: ExecutionRequested) -> ExecutionHeartbeat:
        return ExecutionHeartbeat(executionId=job.executionId, workerId=self.worker_id)

    async def process(self, job: ExecutionRequested, emit: Emit) -> ExecutionFinished:
        await emit(self._heartbeat(job))  # first heartbeat: orchestrator moves QUEUED -> RUNNING
        run = asyncio.create_task(asyncio.to_thread(self._safe_run, job))
        while True:
            done, _ = await asyncio.wait({run}, timeout=self.interval)
            if done:
                break
            await emit(self._heartbeat(job))  # T1: heartbeat feeds the orchestrator's watchdog
        finished = build_finished(job, run.result(), self.worker_id)
        await emit(finished)
        log.info("execution %s finished: outcome=%s exit=%s", job.executionId, finished.outcome, finished.exitCode)
        return finished

    def _safe_run(self, job: ExecutionRequested) -> SandboxResult:
        try:
            return self.sandbox.run(job)
        except Exception as e:  # noqa: BLE001 — any driver bug becomes an ERROR outcome, never a pass
            log.exception("sandbox crashed for %s", job.executionId)
            return SandboxResult(outcome="ERROR", error_detail=f"{type(e).__name__}: {e}"[:2000])
