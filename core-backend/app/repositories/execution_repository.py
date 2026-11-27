"""C4 L3: Execution Repository — the ONLY place that writes execution status (ADR-004, ADR-006).

Used for writes only by the Execution Orchestrator (enforced by .importlinter contract "status-writer").
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import (
    ApprovalDecision,
    EvidenceType,
    ExecutionStatus,
    TerminationReason,
    TestCaseStatus,
    TestResultStatus,
)
from app.repositories.models import (
    Execution,
    ExecutionEvidence,
    ExecutionTestCase,
    ProcessedMessage,
    TestApproval,
    TestCase,
)


class NotApproved(Exception):
    def __init__(self, test_case_ids: list[int]):
        self.test_case_ids = test_case_ids


class UnknownTests(Exception):
    def __init__(self, test_case_ids: list[int]):
        self.test_case_ids = test_case_ids


class ExecutionRepository:
    def __init__(self, session: Session):
        self.s = session

    # ---------- run creation: approval check + insert in ONE transaction (ASR-3, M2 §3.3 msg 4-6) ----------
    def create_execution_if_approved(
        self, project_id: int, test_case_ids: list[int], requested_by: int, time_limit_seconds: int
    ) -> tuple[Execution, list[TestCase]]:
        ids = list(dict.fromkeys(test_case_ids))
        # Lock the test rows so an edit cannot slip between the check and the insert (no-op on SQLite).
        tests = self.s.scalars(
            select(TestCase).where(TestCase.test_case_id.in_(ids), TestCase.project_id == project_id).with_for_update()
        ).all()
        found = {t.test_case_id for t in tests}
        missing = [i for i in ids if i not in found]
        if missing:
            raise UnknownTests(missing)

        approved: dict[int, set[int]] = {}
        for tc_id, ver in self.s.execute(
            select(TestApproval.test_case_id, TestApproval.test_case_version).where(
                TestApproval.test_case_id.in_(ids), TestApproval.decision == ApprovalDecision.APPROVED
            )
        ).all():
            approved.setdefault(tc_id, set()).add(ver)

        not_ok = [
            t.test_case_id
            for t in tests
            if t.status != TestCaseStatus.APPROVED or t.version not in approved.get(t.test_case_id, set())
        ]
        if not_ok:
            raise NotApproved(sorted(not_ok))

        execution = Execution(
            execution_id=uuid.uuid4(),
            project_id=project_id,
            requested_by=requested_by,
            status=ExecutionStatus.QUEUED,
            time_limit_seconds=time_limit_seconds,
        )
        self.s.add(execution)
        self.s.flush()
        by_id = {t.test_case_id: t for t in tests}
        ordered = [by_id[i] for i in ids]
        for t in ordered:
            self.s.add(
                ExecutionTestCase(
                    execution_id=execution.execution_id, test_case_id=t.test_case_id, test_case_version=t.version
                )
            )
        self.s.flush()
        self.s.refresh(execution)
        return execution, ordered

    # ---------- lifecycle ----------
    def get_for_update(self, execution_id: uuid.UUID) -> Execution | None:
        return self.s.scalar(select(Execution).where(Execution.execution_id == execution_id).with_for_update())

    def mark_running(self, execution: Execution, at: datetime) -> None:
        execution.status = ExecutionStatus.RUNNING
        execution.started_at = execution.started_at or at
        execution.last_heartbeat_at = at

    def touch_heartbeat(self, execution: Execution, at: datetime) -> None:
        execution.last_heartbeat_at = at

    def message_processed(self, message_id: uuid.UUID) -> bool:
        return self.s.get(ProcessedMessage, message_id) is not None

    def record_message(self, message_id: uuid.UUID, execution_id: uuid.UUID) -> None:
        self.s.add(ProcessedMessage(message_id=message_id, execution_id=execution_id))

    def save_terminal_status(
        self,
        execution: Execution,
        status: ExecutionStatus,
        reason: TerminationReason,
        at: datetime,
        test_results: dict[int, tuple[TestResultStatus, int | None, str | None]],
        evidence: list[tuple[EvidenceType, str, int, bool]],
    ) -> None:
        """Write status + per-test results + evidence together (tactic T6). Caller commits once."""
        assert status.is_terminal
        execution.status = status
        execution.termination_reason = reason
        execution.finished_at = at
        for etc in execution.tests:
            res = test_results.get(etc.test_case_id)
            if res:
                etc.result_status, etc.duration_ms, etc.failure_message = res
            else:
                etc.result_status = TestResultStatus.NOT_RUN
        for ev_type, content, size, truncated in evidence:
            self.s.add(
                ExecutionEvidence(
                    execution_id=execution.execution_id,
                    evidence_type=ev_type,
                    content=content,
                    size_bytes=size,
                    truncated=truncated,
                )
            )
        self.s.flush()

    def active_executions(self) -> list[Execution]:
        return list(
            self.s.scalars(
                select(Execution).where(Execution.status == ExecutionStatus.RUNNING).with_for_update(skip_locked=True)
            ).all()
        )
