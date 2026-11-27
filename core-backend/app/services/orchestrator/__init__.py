"""C4 L3: Execution Orchestrator — the ONLY component that writes execution status (ASR-3, ADR-006).

Inbound calls:
  * start_run()       — from the Execution & Results API (POST /api/executions)
  * on_heartbeat()    — from the Execution Event Listener (AMQP, Member 2)
  * on_finished()     — from the Execution Event Listener (AMQP, Member 2)
  * sweep()           — from the watchdog loop (watchdog.py)

Contract for the listener (Member 2): validate the raw JSON into ExecutionHeartbeat / ExecutionFinished
(app.core.messages), call the handler, and ack the AMQP message only AFTER the handler returns
(it has committed). If the handler raises, nack/requeue. Handlers are idempotent.
"""

import logging
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.actor import Actor
from app.core.config import Settings
from app.core.enums import EvidenceType, ExecutionStatus, TerminationReason, TestResultStatus
from app.core.errors import Conflict, QueueUnavailable, ValidationFailed
from app.core.messages import ExecutionFinished, ExecutionHeartbeat, ExecutionRequested, Limits, RequestedTest
from app.core.timeutil import as_utc, utcnow
from app.integration.job_publisher import JobPublisher, PublishFailed
from app.repositories.execution_repository import ExecutionRepository, NotApproved, UnknownTests
from app.repositories.models import Execution
from app.repositories.project_repository import ProjectRepository
from app.services._access import require_member
from app.services.orchestrator.report_validator import evaluate
from app.services.orchestrator.state_machine import can_move

log = logging.getLogger(__name__)


def _cap(text: str, max_bytes: int) -> tuple[str, int, bool]:
    raw = text.encode("utf-8", errors="replace")
    if len(raw) <= max_bytes:
        return text, len(raw), False
    marker = "\n...[truncated by TestPilot]"
    cut = raw[: max(0, max_bytes - len(marker))].decode("utf-8", errors="ignore")
    return cut + marker, len(raw), True


class ExecutionOrchestrator:
    def __init__(self, session: Session, publisher: JobPublisher, settings: Settings):
        self.s = session
        self.publisher = publisher
        self.settings = settings
        self.executions = ExecutionRepository(session)
        self.projects = ProjectRepository(session)

    # ------------------------------------------------------------------ start a run (UC-3)
    def start_run(self, actor: Actor, project_id: int, test_case_ids: list[int]) -> Execution:
        require_member(self.projects, actor, project_id)
        try:
            execution, tests = self.executions.create_execution_if_approved(
                project_id, test_case_ids, actor.user_id, self.settings.run_time_limit_seconds
            )
        except NotApproved as e:
            self.s.rollback()
            raise Conflict(
                f"Test(s) {e.test_case_ids} are not approved in their current version.",
                details={"testCaseIds": e.test_case_ids},
                code="TEST_NOT_APPROVED",
            ) from e
        except UnknownTests as e:
            self.s.rollback()
            raise ValidationFailed(
                f"Test(s) {e.test_case_ids} do not exist in project {project_id}",
                details={"testCaseIds": e.test_case_ids},
            ) from e

        message = ExecutionRequested(
            executionId=execution.execution_id,
            projectId=project_id,
            tests=[
                RequestedTest(testCaseId=t.test_case_id, testCaseVersion=t.version, testCode=t.test_code) for t in tests
            ],
            limits=Limits(
                timeSeconds=self.settings.run_time_limit_seconds,
                cpu=self.settings.run_cpu,
                memoryMb=self.settings.run_memory_mb,
            ),
        )
        try:
            self.publisher.publish(message)
        except PublishFailed as e:
            # No orphan QUEUED row: the execution insert is rolled back (contract 503 QUEUE_UNAVAILABLE).
            self.s.rollback()
            raise QueueUnavailable("The execution queue is unavailable. Please try again shortly.") from e
        self.s.commit()
        return execution

    # ------------------------------------------------------------------ worker events
    def on_heartbeat(self, msg: ExecutionHeartbeat) -> None:
        ex = self.executions.get_for_update(msg.executionId)
        if ex is None or ex.status.is_terminal:
            log.info("heartbeat ignored for %s (unknown or terminal)", msg.executionId)
            self.s.rollback()
            return
        now = utcnow()
        if ex.status == ExecutionStatus.QUEUED:
            self.executions.mark_running(ex, now)
        else:
            self.executions.touch_heartbeat(ex, now)
        self.s.commit()

    def on_finished(self, msg: ExecutionFinished) -> ExecutionStatus | None:
        """Validate the runner output and write the terminal status + evidence in one transaction."""
        if self.executions.message_processed(msg.messageId):
            log.info("duplicate ExecutionFinished %s ignored", msg.messageId)
            return None
        ex = self.executions.get_for_update(msg.executionId)
        if ex is None:
            log.warning("ExecutionFinished for unknown execution %s ignored", msg.executionId)
            self.s.rollback()
            return None
        if ex.status.is_terminal:
            # late or duplicate result (e.g. requeued job after RUNNER_LOST) can never overwrite a terminal state
            self.executions.record_message(msg.messageId, ex.execution_id)
            self.s.commit()
            log.info("late ExecutionFinished for terminal execution %s ignored", ex.execution_id)
            return None

        expected = {t.test_case_id: t.test_case_version for t in ex.tests}
        verdict = evaluate(msg, expected)
        now = utcnow()
        if ex.status == ExecutionStatus.QUEUED:  # finished without any heartbeat reaching us
            ex.started_at = now
        assert can_move(ExecutionStatus.RUNNING, verdict.status)

        cap = self.settings.evidence_max_bytes
        evidence = []
        for ev_type, text in (
            (EvidenceType.STDOUT, msg.stdout),
            (EvidenceType.STDERR, msg.stderr),
            (EvidenceType.JUNIT_XML, msg.junitXml or ""),
        ):
            if text:
                content, size, truncated = _cap(text, cap)
                evidence.append(
                    (ev_type, content, size, truncated or (msg.truncated and ev_type != EvidenceType.JUNIT_XML))
                )
        runner_log = (
            f"worker={msg.workerId} outcome={msg.outcome} exitCode={msg.exitCode} durationMs={msg.durationMs} "
            f"verdict={verdict.status.value}/{verdict.reason.value}" + (f" note={verdict.note}" if verdict.note else "")
        )
        evidence.append((EvidenceType.RUNNER_LOG, runner_log, len(runner_log.encode()), False))

        self.executions.save_terminal_status(ex, verdict.status, verdict.reason, now, verdict.results, evidence)
        self.executions.record_message(msg.messageId, ex.execution_id)
        self.s.commit()
        return verdict.status

    # ------------------------------------------------------------------ watchdog (T1)
    def sweep(self, now=None) -> list[tuple[str, TerminationReason]]:
        """Interrupt RUNNING executions whose heartbeats stopped or whose time limit passed."""
        now = now or utcnow()
        hb_window = timedelta(
            seconds=self.settings.heartbeat_interval_seconds * self.settings.watchdog_missed_heartbeats
        )
        grace = timedelta(seconds=self.settings.watchdog_timeout_grace_seconds)
        interrupted: list[tuple[str, TerminationReason]] = []
        for ex in self.executions.active_executions():
            started = as_utc(ex.started_at)
            last_hb = as_utc(ex.last_heartbeat_at) or started
            reason = None
            if started and now > started + timedelta(seconds=ex.time_limit_seconds) + grace + hb_window:
                reason = TerminationReason.TIMEOUT
            elif last_hb and now - last_hb > hb_window:
                reason = TerminationReason.RUNNER_LOST
            if reason:
                note = f"watchdog: {reason.value} (last heartbeat {last_hb.isoformat() if last_hb else 'never'})"
                self.executions.save_terminal_status(
                    ex,
                    ExecutionStatus.INTERRUPTED,
                    reason,
                    now,
                    {t.test_case_id: (TestResultStatus.NOT_RUN, None, None) for t in ex.tests},
                    [(EvidenceType.RUNNER_LOG, note, len(note), False)],
                )
                interrupted.append((str(ex.execution_id), reason))
        self.s.commit()
        return interrupted
