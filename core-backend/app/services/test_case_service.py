"""C4 L3: Test Case & Approval Service (FR-03..FR-05).

* AI suggestions are stored as DRAFT, source AI_GENERATED (human-in-the-loop).
* Any edit bumps the version and resets the status to DRAFT (ADR-005: approval is bound to a version).
* Approve/reject must name the version the reviewer looked at; a stale version -> 409 VERSION_CONFLICT.
* If the AI is unavailable the error propagates as AI_UNAVAILABLE; manual entry keeps working (T4).
"""

import ast

from sqlalchemy.orm import Session

from app.core.actor import Actor
from app.core.enums import ApprovalDecision, TestCaseStatus, TestSource, TestType
from app.core.errors import AiUnavailable, Conflict, NotFound, ValidationFailed
from app.core.timeutil import utcnow
from app.integration.ai_client import AiServiceClient
from app.repositories.models import Requirement, ReviewFlag, TestApproval, TestCase
from app.repositories.project_repository import ProjectRepository
from app.repositories.test_case_repository import TestCaseRepository
from app.services._access import page_args, require_member


def check_test_code(code: str) -> None:
    """Sanity check (T2): valid Python that defines at least one pytest test function."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise ValidationFailed("testCode is not valid Python", details={"line": e.lineno, "error": e.msg}) from e
    if not any(
        isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name.startswith("test") for n in ast.walk(tree)
    ):
        raise ValidationFailed("testCode must define at least one function whose name starts with 'test'")


class TestCaseService:
    __test__ = False

    def __init__(self, session: Session, ai: AiServiceClient | None):
        self.s = session
        self.ai = ai
        self.projects = ProjectRepository(session)
        self.tests = TestCaseRepository(session)

    # ---------- helpers ----------
    def _requirements(self, project_id: int, ids: list[int]) -> list[Requirement]:
        reqs = []
        for rid in dict.fromkeys(ids):
            r = self.projects.get_requirement(rid)
            if r is None or r.project_id != project_id:
                raise ValidationFailed(f"Requirement {rid} does not belong to project {project_id}")
            reqs.append(r)
        return reqs

    def _get_owned(self, actor: Actor, test_id: int) -> TestCase:
        tc = self.tests.get(test_id)
        if tc is None:
            raise NotFound(f"Test case {test_id} not found")
        require_member(self.projects, actor, tc.project_id)
        return tc

    # ---------- FR-03 ----------
    def generate(
        self, actor: Actor, project_id: int, requirement_id: int, test_types: list[TestType], code: str | None
    ) -> list[int]:
        require_member(self.projects, actor, project_id)
        [req] = self._requirements(project_id, [requirement_id])
        if self.ai is None:
            raise AiUnavailable("AI assistance is not configured")
        data = self.ai.suggest_tests(f"{req.title}\n\n{req.description}", [t.value for t in test_types], code)
        ids: list[int] = []
        for sug in data["suggestions"]:
            try:
                test_type = TestType(sug["testType"])
                check_test_code(sug["testCode"])
            except (ValueError, ValidationFailed):
                continue  # invalid model output is never stored (T2)
            tc = self.tests.add(
                TestCase(
                    project_id=project_id,
                    title=str(sug["title"])[:200],
                    description=sug.get("description"),
                    test_type=test_type,
                    source=TestSource.AI_GENERATED,
                    test_code=sug["testCode"],
                    status=TestCaseStatus.DRAFT,
                    version=1,
                    created_by=actor.user_id,
                ),
                [req],
            )
            ids.append(tc.test_case_id)
        self.s.commit()
        return ids

    # ---------- manual entry (Phase 1 addition, ADR-009) ----------
    def create_manual(
        self,
        actor: Actor,
        project_id: int,
        title: str,
        description: str | None,
        test_type: TestType,
        test_code: str,
        requirement_ids: list[int],
    ) -> TestCase:
        require_member(self.projects, actor, project_id)
        check_test_code(test_code)
        tc = self.tests.add(
            TestCase(
                project_id=project_id,
                title=title.strip(),
                description=description,
                test_type=test_type,
                source=TestSource.MANUAL,
                test_code=test_code,
                status=TestCaseStatus.DRAFT,
                version=1,
                created_by=actor.user_id,
            ),
            self._requirements(project_id, requirement_ids),
        )
        self.s.commit()
        return tc

    # ---------- FR-04 ----------
    def list_tests(
        self, actor: Actor, project_id: int, status: TestCaseStatus | None, page: int, size: int
    ) -> tuple[list[TestCase], int]:
        require_member(self.projects, actor, project_id)
        offset, limit = page_args(page, size)
        return self.tests.list_page(project_id, status, offset, limit)

    def get(self, actor: Actor, test_id: int) -> TestCase:
        return self._get_owned(actor, test_id)

    def approved_version(self, tc: TestCase) -> int | None:
        if tc.status != TestCaseStatus.APPROVED:
            return None
        return (
            tc.version
            if tc.version in self.tests.approved_versions([tc.test_case_id]).get(tc.test_case_id, set())
            else None
        )

    def update(self, actor: Actor, test_id: int, changes: dict) -> TestCase:
        tc = self._get_owned(actor, test_id)
        if not changes:
            raise ValidationFailed("Nothing to update")
        if "test_code" in changes:
            check_test_code(changes["test_code"])
        for k, v in changes.items():
            setattr(tc, k, v)
        tc.version += 1
        tc.status = TestCaseStatus.DRAFT  # edited test must be approved again (ADR-005)
        tc.updated_at = utcnow()
        self.s.commit()
        return tc

    def flag(self, actor: Actor, test_id: int, comment: str) -> ReviewFlag:
        tc = self._get_owned(actor, test_id)
        flag = self.tests.add_flag(ReviewFlag(test_case_id=tc.test_case_id, comment=comment, raised_by=actor.user_id))
        self.s.commit()
        return flag

    # ---------- FR-05 ----------
    def decide(
        self, actor: Actor, test_id: int, version: int, decision: ApprovalDecision, comment: str | None
    ) -> TestCase:
        tc = self._get_owned(actor, test_id)
        if version != tc.version:
            raise Conflict(
                f"Test {test_id} is at version {tc.version}, you reviewed version {version}. Reload and review again.",
                details={"currentVersion": tc.version},
                code="VERSION_CONFLICT",
            )
        target = TestCaseStatus.APPROVED if decision == ApprovalDecision.APPROVED else TestCaseStatus.REJECTED
        if tc.status == target:
            raise Conflict(f"Test {test_id} version {version} is already {target.value}", code="INVALID_STATE")
        self.tests.add_approval(
            TestApproval(
                test_case_id=tc.test_case_id,
                test_case_version=tc.version,
                decision=decision,
                comment=comment,
                decided_by=actor.user_id,
            )
        )
        tc.status = target
        tc.updated_at = utcnow()
        self.s.commit()
        return tc
