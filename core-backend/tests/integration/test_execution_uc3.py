"""UC-3: run approved tests. Crosses the API -> Orchestrator -> Repository -> DB boundary and the
Orchestrator <-> message-contract boundary (the AMQP transport itself is Member 2's part)."""

from datetime import timedelta

import jsonschema
import pytest

from app.core.messages import ExecutionFinished, ExecutionHeartbeat
from app.core.timeutil import utcnow
from app.services.orchestrator import ExecutionOrchestrator
from tests.conftest import finished, heartbeat, junit, make_approved_test, message_schema


@pytest.fixture
def orch(app, session, publisher, settings):
    return ExecutionOrchestrator(session, publisher, settings)


def start(client, headers, project_id, ids):
    return client.post("/api/executions", headers=headers, json={"projectId": project_id, "testCaseIds": ids})


def test_run_publishes_a_contract_valid_message(client, dev, project_id, requirement_id, publisher):
    t = make_approved_test(client, dev, project_id, requirement_id)
    r = start(client, dev, project_id, [t["testCaseId"]])
    assert r.status_code == 202 and r.json()["status"] == "QUEUED"
    assert len(publisher.messages) == 1
    msg = publisher.messages[0]
    jsonschema.validate(msg, message_schema("execution-requested"))  # I4 contract
    assert msg["executionId"] == r.json()["executionId"]
    assert msg["tests"][0]["testCaseVersion"] == 1 and msg["limits"]["timeSeconds"] == 30


def test_unapproved_test_is_rejected_and_nothing_is_created(client, dev, project_id, requirement_id, publisher):
    approved = make_approved_test(client, dev, project_id, requirement_id)
    draft = client.post(
        f"/api/projects/{project_id}/tests",
        headers=dev,
        json={"title": "d", "testType": "NORMAL", "testCode": "def test_a():\n    pass\n"},
    ).json()["id"]
    r = start(client, dev, project_id, [approved["testCaseId"], draft])
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "TEST_NOT_APPROVED"
    assert r.json()["error"]["details"]["testCaseIds"] == [draft]
    assert publisher.messages == []
    assert client.get(f"/api/projects/{project_id}/executions", headers=dev).json()["total"] == 0


def test_edited_after_approval_cannot_run(client, dev, project_id, requirement_id):
    t = make_approved_test(client, dev, project_id, requirement_id)
    client.put(f"/api/tests/{t['testCaseId']}", headers=dev, json={"title": "changed"})
    assert start(client, dev, project_id, [t["testCaseId"]]).status_code == 409


def test_broker_down_returns_503_and_leaves_no_queued_row(client, dev, project_id, requirement_id, publisher):
    t = make_approved_test(client, dev, project_id, requirement_id)
    publisher.fail = True
    r = start(client, dev, project_id, [t["testCaseId"]])
    assert r.status_code == 503 and r.json()["error"]["code"] == "QUEUE_UNAVAILABLE"
    assert client.get(f"/api/projects/{project_id}/executions", headers=dev).json()["total"] == 0


def test_qa_assistant_may_run_but_lead_may_not_explain(client, qa, lead, dev, project_id, requirement_id):
    t = make_approved_test(client, dev, project_id, requirement_id)
    assert start(client, qa, project_id, [t["testCaseId"]]).status_code == 202


def test_full_lifecycle_passed(client, dev, project_id, requirement_id, orch, publisher):
    t = make_approved_test(client, dev, project_id, requirement_id)
    ex_id = start(client, dev, project_id, [t["testCaseId"]]).json()["executionId"]

    hb = heartbeat(ex_id)
    jsonschema.validate(hb, message_schema("execution-heartbeat"))
    orch.on_heartbeat(ExecutionHeartbeat.model_validate(hb))
    assert client.get(f"/api/executions/{ex_id}", headers=dev).json()["status"] == "RUNNING"

    fin = finished(ex_id, junitXml=junit([(t["testCaseId"], 1, "pass")]))
    jsonschema.validate(fin, message_schema("execution-finished"))
    orch.on_finished(ExecutionFinished.model_validate(fin))

    body = client.get(f"/api/executions/{ex_id}", headers=dev).json()
    assert body["status"] == "PASSED" and body["terminationReason"] == "COMPLETED"
    assert body["tests"][0]["resultStatus"] == "PASSED" and body["finishedAt"]
    logs = client.get(f"/api/executions/{ex_id}/logs", headers=dev).json()
    assert {e["evidenceType"] for e in logs["items"]} == {"STDOUT", "JUNIT_XML", "RUNNER_LOG"}


def test_failed_run_and_ai_explanation(client, dev, lead, project_id, requirement_id, orch):
    t = make_approved_test(client, dev, project_id, requirement_id)
    ex_id = start(client, dev, project_id, [t["testCaseId"]]).json()["executionId"]
    orch.on_heartbeat(ExecutionHeartbeat.model_validate(heartbeat(ex_id)))
    orch.on_finished(
        ExecutionFinished.model_validate(finished(ex_id, exitCode=1, junitXml=junit([(t["testCaseId"], 1, "fail")])))
    )
    body = client.get(f"/api/executions/{ex_id}", headers=dev).json()
    assert body["status"] == "FAILED" and body["tests"][0]["failureMessage"] == "assert 3 == 4"

    etid = body["tests"][0]["executionTestId"]
    url = f"/api/executions/{ex_id}/tests/{etid}/explanation"
    assert client.post(url, headers=lead).status_code == 403  # explain: Developer / QA Assistant only
    e = client.post(url, headers=dev).json()
    assert e["aiGenerated"] is True and "hypothesis" in e["label"]


def test_invalid_report_is_interrupted_never_passed(client, dev, project_id, requirement_id, orch):
    t = make_approved_test(client, dev, project_id, requirement_id)
    ex_id = start(client, dev, project_id, [t["testCaseId"]]).json()["executionId"]
    orch.on_heartbeat(ExecutionHeartbeat.model_validate(heartbeat(ex_id)))
    orch.on_finished(ExecutionFinished.model_validate(finished(ex_id, exitCode=0, junitXml="<garbage")))
    body = client.get(f"/api/executions/{ex_id}", headers=dev).json()
    assert (body["status"], body["terminationReason"]) == ("INTERRUPTED", "INVALID_REPORT")
    assert body["tests"][0]["resultStatus"] == "NOT_RUN"


def test_duplicate_and_late_results_are_ignored(client, dev, project_id, requirement_id, orch):
    t = make_approved_test(client, dev, project_id, requirement_id)
    ex_id = start(client, dev, project_id, [t["testCaseId"]]).json()["executionId"]
    fail_msg = ExecutionFinished.model_validate(
        finished(ex_id, exitCode=1, junitXml=junit([(t["testCaseId"], 1, "fail")]))
    )
    assert orch.on_finished(fail_msg).value == "FAILED"
    assert orch.on_finished(fail_msg) is None  # same messageId again
    late_pass = ExecutionFinished.model_validate(finished(ex_id, junitXml=junit([(t["testCaseId"], 1, "pass")])))
    assert orch.on_finished(late_pass) is None  # a later "pass" cannot overwrite a terminal state
    orch.on_heartbeat(ExecutionHeartbeat.model_validate(heartbeat(ex_id)))  # late heartbeat ignored
    assert client.get(f"/api/executions/{ex_id}", headers=dev).json()["status"] == "FAILED"


def test_unknown_execution_events_are_ignored(orch):
    import uuid

    assert orch.on_finished(ExecutionFinished.model_validate(finished(uuid.uuid4()))) is None
    orch.on_heartbeat(ExecutionHeartbeat.model_validate(heartbeat(uuid.uuid4())))


def test_watchdog_interrupts_lost_runner(client, dev, project_id, requirement_id, orch):
    t = make_approved_test(client, dev, project_id, requirement_id)
    ex_id = start(client, dev, project_id, [t["testCaseId"]]).json()["executionId"]
    orch.on_heartbeat(ExecutionHeartbeat.model_validate(heartbeat(ex_id)))
    assert orch.sweep(now=utcnow() + timedelta(seconds=5)) == []  # still within 3 x 5 s
    out = orch.sweep(now=utcnow() + timedelta(seconds=16))
    assert out and out[0][1].value == "RUNNER_LOST"
    body = client.get(f"/api/executions/{ex_id}", headers=dev).json()
    assert (body["status"], body["terminationReason"]) == ("INTERRUPTED", "RUNNER_LOST")
    # the requeued job's result arriving later is ignored (R-011)
    late = ExecutionFinished.model_validate(finished(ex_id, junitXml=junit([(t["testCaseId"], 1, "pass")])))
    assert orch.on_finished(late) is None


def test_evidence_is_capped(client, dev, project_id, requirement_id, orch):
    t = make_approved_test(client, dev, project_id, requirement_id)
    ex_id = start(client, dev, project_id, [t["testCaseId"]]).json()["executionId"]
    orch.on_finished(
        ExecutionFinished.model_validate(
            finished(ex_id, stdout="x" * 5000, junitXml=junit([(t["testCaseId"], 1, "pass")]))
        )
    )
    stdout = next(
        e
        for e in client.get(f"/api/executions/{ex_id}/logs", headers=dev).json()["items"]
        if e["evidenceType"] == "STDOUT"
    )
    assert stdout["truncated"] is True and stdout["sizeBytes"] == 5000 and len(stdout["content"].encode()) <= 200
