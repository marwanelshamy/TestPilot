"""UC-4 (stretch): coverage, rule-based risks and quality report."""

from app.core.messages import ExecutionFinished
from app.services.orchestrator import ExecutionOrchestrator
from tests.conftest import finished, junit, make_approved_test


def test_coverage_risks_and_report(client, dev, lead, qa, project_id, requirement_id, session, publisher, settings):
    # a second requirement with no test -> UNTESTED_REQUIREMENT
    client.post(f"/api/projects/{project_id}/requirements", headers=dev, json={"title": "subtract", "description": "-"})
    t = make_approved_test(client, dev, project_id, requirement_id)
    ex_id = client.post(
        "/api/executions", headers=dev, json={"projectId": project_id, "testCaseIds": [t["testCaseId"]]}
    ).json()["executionId"]
    ExecutionOrchestrator(session, publisher, settings).on_finished(
        ExecutionFinished.model_validate(finished(ex_id, exitCode=1, junitXml=junit([(t["testCaseId"], 1, "fail")])))
    )

    cov = client.get(f"/api/projects/{project_id}/coverage", headers=qa).json()["requirements"]
    assert [(c["approvedTestCount"], c["lastResult"]) for c in cov] == [(1, "FAILED"), (0, None)]

    risks = client.get(f"/api/projects/{project_id}/risks", headers=lead).json()["risks"]
    assert [r["rule"] for r in risks] == ["FAILED_TEST", "UNTESTED_REQUIREMENT"]

    assert client.post(f"/api/projects/{project_id}/reports", headers=dev).status_code == 403  # Team Lead only
    rid = client.post(f"/api/projects/{project_id}/reports", headers=lead).json()["id"]
    rep = client.get(f"/api/reports/{rid}", headers=dev).json()["summary"]
    assert rep["totals"]["requirements"] == 2 and rep["totals"]["latestFailed"] == 1
    assert len(rep["risks"]) == 2 and "not a guarantee" in rep["disclaimer"]
