"""C4 L3: Results & Reporting Service (FR-07..FR-12). Reads execution data; never writes status.

* Coverage (FR-10): requirements and how many APPROVED tests cover them.
* Risks (FR-11, ADR-008): transparent rules — FAILED_TEST (HIGH), UNTESTED_REQUIREMENT (MEDIUM),
  INTERRUPTED_RUN (LOW).
* Explanations (FR-09) are stored and returned labelled as AI hypotheses (C-10).
"""

import uuid

from sqlalchemy.orm import Session

from app.core.actor import Actor
from app.core.enums import EvidenceType, TestResultStatus
from app.core.errors import AiUnavailable, Conflict, NotFound
from app.core.timeutil import utcnow
from app.integration.ai_client import AiServiceClient
from app.repositories.models import AiExplanation, Execution, ExecutionEvidence, QualityReport
from app.repositories.project_repository import ProjectRepository
from app.repositories.results_repository import ResultsRepository
from app.services._access import page_args, require_member

AI_LABEL = "AI-generated hypothesis — verify against the logs"


class ResultsService:
    def __init__(self, session: Session, ai: AiServiceClient | None):
        self.s = session
        self.ai = ai
        self.results = ResultsRepository(session)
        self.projects = ProjectRepository(session)

    # ---------- FR-07 / FR-08 ----------
    def get_execution(self, actor: Actor, execution_id: uuid.UUID) -> Execution:
        ex = self.results.get_execution(execution_id)
        if ex is None:
            raise NotFound(f"Execution {execution_id} not found")
        require_member(self.projects, actor, ex.project_id)
        return ex

    def list_executions(self, actor: Actor, project_id: int, page: int, size: int) -> tuple[list[Execution], int]:
        require_member(self.projects, actor, project_id)
        offset, limit = page_args(page, size)
        return self.results.list_executions(project_id, offset, limit)

    def logs(self, actor: Actor, execution_id: uuid.UUID, page: int, size: int) -> tuple[list[ExecutionEvidence], int]:
        self.get_execution(actor, execution_id)
        offset, limit = page_args(page, size)
        return self.results.list_evidence(execution_id, offset, limit)

    # ---------- FR-10 ----------
    def coverage(self, actor: Actor, project_id: int) -> list[dict]:
        require_member(self.projects, actor, project_id)
        latest = self.results.latest_result_per_test(project_id)
        links = self.results.requirement_links(project_id)
        out = []
        for req, n_approved in self.results.requirement_coverage(project_id):
            results = [latest[t].result_status for t in links.get(req.requirement_id, []) if t in latest]
            if not results:
                last = None
            elif any(r in (TestResultStatus.FAILED, TestResultStatus.ERROR) for r in results):
                last = "FAILED"
            elif all(r == TestResultStatus.PASSED for r in results):
                last = "PASSED"
            else:
                last = "PARTIAL"
            out.append(
                {
                    "requirementId": req.requirement_id,
                    "title": req.title,
                    "approvedTestCount": n_approved,
                    "lastResult": last,
                }
            )
        return out

    # ---------- FR-11 ----------
    def risks(self, actor: Actor, project_id: int) -> list[dict]:
        cov = self.coverage(actor, project_id)
        risks: list[dict] = []
        for t_id, etc in self.results.latest_result_per_test(project_id).items():
            if etc.result_status in (TestResultStatus.FAILED, TestResultStatus.ERROR):
                risks.append(
                    {
                        "rule": "FAILED_TEST",
                        "severity": "HIGH",
                        "refId": f"test:{t_id}",
                        "message": (
                            f"Test {t_id} v{etc.test_case_version} {etc.result_status.value.lower()} in its latest run"
                        ),
                    }
                )
        for c in cov:
            if c["approvedTestCount"] == 0:
                risks.append(
                    {
                        "rule": "UNTESTED_REQUIREMENT",
                        "severity": "MEDIUM",
                        "refId": f"requirement:{c['requirementId']}",
                        "message": f"Requirement '{c['title']}' has no approved test",
                    }
                )
        for ex in self.results.interrupted_runs(project_id, limit=5):
            risks.append(
                {
                    "rule": "INTERRUPTED_RUN",
                    "severity": "LOW",
                    "refId": f"execution:{ex.execution_id}",
                    "message": f"Run interrupted ({ex.termination_reason.value if ex.termination_reason else '?'})",
                }
            )
        order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        return sorted(risks, key=lambda r: order[r["severity"]])

    # ---------- FR-12 ----------
    def generate_report(self, actor: Actor, project_id: int) -> QualityReport:
        coverage = self.coverage(actor, project_id)
        risks = self.risks(actor, project_id)
        latest = self.results.latest_result_per_test(project_id)
        per_result: dict[str, int] = {}
        for etc in latest.values():
            per_result[etc.result_status.value] = per_result.get(etc.result_status.value, 0) + 1
        summary = {
            "generatedAt": utcnow().isoformat(),
            "totals": {
                "requirements": len(coverage),
                "requirementsWithApprovedTests": sum(1 for c in coverage if c["approvedTestCount"] > 0),
                "testsWithResults": len(latest),
                **{f"latest{k.title()}": v for k, v in per_result.items()},
                **{f"executions{k.title()}": v for k, v in self.results.status_counts(project_id).items()},
            },
            "coverage": coverage,
            "risks": risks,
            "disclaimer": "Evidence summary for human release review; not a guarantee of correctness (C-10).",
        }
        report = self.results.add_report(
            QualityReport(project_id=project_id, summary=summary, generated_by=actor.user_id)
        )
        self.s.commit()
        return report

    def get_report(self, actor: Actor, report_id: int) -> QualityReport:
        r = self.results.get_report(report_id)
        if r is None:
            raise NotFound(f"Report {report_id} not found")
        require_member(self.projects, actor, r.project_id)
        return r

    # ---------- FR-09 ----------
    def explain(self, actor: Actor, execution_id: uuid.UUID, execution_test_id: int) -> AiExplanation:
        ex = self.get_execution(actor, execution_id)
        etc = self.results.get_execution_test(execution_test_id)
        if etc is None or etc.execution_id != ex.execution_id:
            raise NotFound(f"Test result {execution_test_id} not found in execution {execution_id}")
        if etc.result_status not in (TestResultStatus.FAILED, TestResultStatus.ERROR):
            raise Conflict("Only failed or errored tests can be explained", code="INVALID_STATE")
        if self.ai is None:
            raise AiUnavailable("AI assistance is not configured")
        tc = self.results.get_test_case(etc.test_case_id)
        evidence, _ = self.results.list_evidence(ex.execution_id, 0, 10)
        log_excerpt = "\n".join(
            e.content[:3000] for e in evidence if e.evidence_type in (EvidenceType.STDOUT, EvidenceType.STDERR)
        )
        data = self.ai.explain_failure(tc.test_code if tc else "", etc.failure_message or "", log_excerpt)
        exp = self.results.add_explanation(
            AiExplanation(
                execution_test_id=etc.execution_test_id,
                explanation_text=data["explanationText"],
                provider_model=str(data.get("providerModel", "unknown"))[:120],
                requested_by=actor.user_id,
            )
        )
        self.s.commit()
        return exp
