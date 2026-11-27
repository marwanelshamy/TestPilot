"""C4 L3: Test Case Repository — test cases, requirement links, approvals and flags (P7)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import ApprovalDecision, TestCaseStatus
from app.repositories.models import Requirement, ReviewFlag, TestApproval, TestCase


class TestCaseRepository:
    __test__ = False

    def __init__(self, session: Session):
        self.s = session

    def add(self, tc: TestCase, requirements: list[Requirement]) -> TestCase:
        tc.requirements = list(requirements)
        self.s.add(tc)
        self.s.flush()
        return tc

    def get(self, test_case_id: int) -> TestCase | None:
        return self.s.get(TestCase, test_case_id)

    def list_page(
        self, project_id: int, status: TestCaseStatus | None, offset: int, limit: int
    ) -> tuple[list[TestCase], int]:
        base = select(TestCase).where(TestCase.project_id == project_id)
        if status:
            base = base.where(TestCase.status == status)
        total = self.s.scalar(select(func.count()).select_from(base.subquery())) or 0
        rows = self.s.scalars(base.order_by(TestCase.test_case_id).offset(offset).limit(limit)).all()
        return list(rows), total

    def add_approval(self, approval: TestApproval) -> TestApproval:
        self.s.add(approval)
        self.s.flush()
        return approval

    def approved_versions(self, test_case_ids: list[int]) -> dict[int, set[int]]:
        rows = self.s.execute(
            select(TestApproval.test_case_id, TestApproval.test_case_version).where(
                TestApproval.test_case_id.in_(test_case_ids), TestApproval.decision == ApprovalDecision.APPROVED
            )
        ).all()
        out: dict[int, set[int]] = {}
        for tc_id, ver in rows:
            out.setdefault(tc_id, set()).add(ver)
        return out

    def add_flag(self, flag: ReviewFlag) -> ReviewFlag:
        self.s.add(flag)
        self.s.flush()
        return flag
