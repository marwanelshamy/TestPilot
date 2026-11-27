"""C4 L3: Results Repository — READ-ONLY queries (indexed, paginated; QAS-1, tactic T15).

Exception: it also inserts AI explanations and quality reports, which are reporting artefacts,
never execution status.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import ExecutionStatus, TestCaseStatus
from app.repositories.models import (
    AiExplanation,
    Execution,
    ExecutionEvidence,
    ExecutionTestCase,
    QualityReport,
    Requirement,
    RequirementTestCase,
    TestCase,
)


class ResultsRepository:
    def __init__(self, session: Session):
        self.s = session

    def get_execution(self, execution_id: uuid.UUID) -> Execution | None:
        return self.s.get(Execution, execution_id)

    def list_executions(self, project_id: int, offset: int, limit: int) -> tuple[list[Execution], int]:
        base = select(Execution).where(Execution.project_id == project_id)
        total = self.s.scalar(select(func.count()).select_from(base.subquery())) or 0
        rows = self.s.scalars(base.order_by(Execution.created_at.desc()).offset(offset).limit(limit)).all()
        return list(rows), total

    def list_evidence(self, execution_id: uuid.UUID, offset: int, limit: int) -> tuple[list[ExecutionEvidence], int]:
        base = select(ExecutionEvidence).where(ExecutionEvidence.execution_id == execution_id)
        total = self.s.scalar(select(func.count()).select_from(base.subquery())) or 0
        rows = self.s.scalars(base.order_by(ExecutionEvidence.evidence_id).offset(offset).limit(limit)).all()
        return list(rows), total

    def get_execution_test(self, execution_test_id: int) -> ExecutionTestCase | None:
        return self.s.get(ExecutionTestCase, execution_test_id)

    def get_test_case(self, test_case_id: int) -> TestCase | None:
        return self.s.get(TestCase, test_case_id)

    def requirement_coverage(self, project_id: int) -> list[tuple[Requirement, int]]:
        """Each requirement with the number of APPROVED tests linked to it (FR-10)."""
        approved = (
            select(RequirementTestCase.requirement_id, func.count(TestCase.test_case_id).label("n"))
            .join(TestCase, TestCase.test_case_id == RequirementTestCase.test_case_id)
            .where(TestCase.status == TestCaseStatus.APPROVED)
            .group_by(RequirementTestCase.requirement_id)
            .subquery()
        )
        rows = self.s.execute(
            select(Requirement, func.coalesce(approved.c.n, 0))
            .outerjoin(approved, approved.c.requirement_id == Requirement.requirement_id)
            .where(Requirement.project_id == project_id)
            .order_by(Requirement.requirement_id)
        ).all()
        return [(r, int(n)) for r, n in rows]

    def latest_result_per_test(self, project_id: int) -> dict[int, ExecutionTestCase]:
        """Most recent terminal result for every test case of the project."""
        rows = self.s.scalars(
            select(ExecutionTestCase)
            .join(Execution)
            .where(
                Execution.project_id == project_id,
                Execution.status.notin_([ExecutionStatus.QUEUED, ExecutionStatus.RUNNING]),
            )
            .order_by(Execution.created_at.desc(), ExecutionTestCase.execution_test_id.desc())
        ).all()
        latest: dict[int, ExecutionTestCase] = {}
        for r in rows:
            latest.setdefault(r.test_case_id, r)
        return latest

    def requirement_links(self, project_id: int) -> dict[int, list[int]]:
        rows = self.s.execute(
            select(RequirementTestCase.requirement_id, RequirementTestCase.test_case_id)
            .join(Requirement)
            .where(Requirement.project_id == project_id)
        ).all()
        out: dict[int, list[int]] = {}
        for req_id, tc_id in rows:
            out.setdefault(req_id, []).append(tc_id)
        return out

    def status_counts(self, project_id: int) -> dict[str, int]:
        rows = self.s.execute(
            select(Execution.status, func.count()).where(Execution.project_id == project_id).group_by(Execution.status)
        ).all()
        return {str(s): int(n) for s, n in rows}

    def interrupted_runs(self, project_id: int, limit: int = 20) -> list[Execution]:
        return list(
            self.s.scalars(
                select(Execution)
                .where(Execution.project_id == project_id, Execution.status == ExecutionStatus.INTERRUPTED)
                .order_by(Execution.created_at.desc())
                .limit(limit)
            ).all()
        )

    # reporting artefacts
    def add_explanation(self, e: AiExplanation) -> AiExplanation:
        self.s.add(e)
        self.s.flush()
        return e

    def add_report(self, r: QualityReport) -> QualityReport:
        self.s.add(r)
        self.s.flush()
        return r

    def get_report(self, report_id: int) -> QualityReport | None:
        return self.s.get(QualityReport, report_id)
