"""Cross-boundary integration test (M3 §5) — the whole prototype, through the public API only.

Crosses every container boundary of the C4 Level 2 view:
    client -> Nginx (Web UI container) -> Core Backend -> PostgreSQL
                                       -> AI Assistance Service (mock provider)
                                       -> RabbitMQ -> Runner Worker -> Test Sandbox -> RabbitMQ -> Core Backend

Run against the composed system (Phase 4):
    docker compose up -d --build
    TESTPILOT_URL=http://127.0.0.1:8080/api python -m pytest tests/e2e -v

Skipped automatically when TESTPILOT_URL is not set, so it never breaks the per-service unit suites.
"""

import os
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "evidence"))
from lib.tp import Api  # noqa: E402

BASE = os.environ.get("TESTPILOT_URL")
pytestmark = pytest.mark.skipif(not BASE, reason="set TESTPILOT_URL to run against the composed system")

CODE = (
    "def add(a, b):\n"
    "    if not isinstance(a, int) or not isinstance(b, int):\n"
    "        raise TypeError('integers only')\n"
    "    return a + b\n"
)
FAILING = CODE + "\n\ndef test_wrong_expectation():\n    assert add(2, 2) == 5\n"


@pytest.fixture(scope="module")
def ctx():
    # A new project's only member is its creator (membership management is FR-13, future work), so the
    # developer drives the flow; the QA Assistant is used only to prove the role check.
    dev, qa = (Api(BASE, timeout=90).login(w) for w in ("dev", "qa"))
    pid = dev.new_project(f"E2E {uuid.uuid4().hex[:6]}")
    rid = dev.new_requirement(pid, "add(a, b) returns the sum of two integers")
    return {"dev": dev, "qa": qa, "pid": pid, "rid": rid}


def test_uc1_project_and_requirement(ctx):
    p = ctx["dev"].ok("GET", f"/projects/{ctx['pid']}")
    assert (p["programmingLanguage"], p["testFramework"]) == ("Python", "pytest")
    assert ctx["dev"].ok("GET", f"/projects/{ctx['pid']}/requirements")["total"] == 1


def test_uc2_ai_generation_crosses_core_and_ai_service(ctx):
    r = ctx["dev"].ok(
        "POST", f"/projects/{ctx['pid']}/tests/generate", {"requirementId": ctx["rid"], "codeUnderTest": CODE}
    )
    assert len(r["testIds"]) >= 1
    t = ctx["dev"].ok("GET", f"/tests/{r['testIds'][0]}")
    assert t["status"] == "DRAFT" and t["aiGenerated"] is True and t["requirementIds"] == [ctx["rid"]]
    ctx["ai_test"] = t["testCaseId"]


def test_uc2_qa_assistant_cannot_approve(ctx):
    assert ctx["qa"].call("POST", f"/tests/{ctx['ai_test']}/approve", {"version": 1}).status_code == 403


def test_uc3_unapproved_test_is_rejected(ctx):
    r = ctx["dev"].call("POST", "/executions", {"projectId": ctx["pid"], "testCaseIds": [ctx["ai_test"]]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "TEST_NOT_APPROVED"


def test_uc3_run_goes_through_broker_runner_and_sandbox(ctx):
    dev = ctx["dev"]
    dev.ok("POST", f"/tests/{ctx['ai_test']}/approve", {"version": 1})
    failing = dev.approved_test(ctx["pid"], FAILING, "wrong expectation", [ctx["rid"]])
    ex = dev.wait_terminal(dev.start_run(ctx["pid"], [ctx["ai_test"], failing]), timeout=180)

    assert ex["status"] == "FAILED" and ex["terminationReason"] == "COMPLETED", ex
    by_id = {t["testCaseId"]: t for t in ex["tests"]}
    assert by_id[ctx["ai_test"]]["resultStatus"] == "PASSED"
    assert by_id[failing]["resultStatus"] == "FAILED" and "assert" in by_id[failing]["failureMessage"]
    kinds = {e["evidenceType"] for e in dev.ok("GET", f"/executions/{ex['executionId']}/logs")["items"]}
    assert {"JUNIT_XML", "STDOUT", "RUNNER_LOG"} <= kinds
    ctx["failed"] = (ex["executionId"], by_id[failing]["executionTestId"])


def test_uc3_ai_explanation_is_labelled(ctx):
    ex_id, etid = ctx["failed"]
    e = ctx["dev"].ok("POST", f"/executions/{ex_id}/tests/{etid}/explanation")
    assert e["aiGenerated"] is True and "hypothesis" in e["label"]


def test_uc4_risks_and_report(ctx):
    risks = ctx["dev"].ok("GET", f"/projects/{ctx['pid']}/risks")["risks"]
    assert any(r["rule"] == "FAILED_TEST" for r in risks)
    cov = ctx["dev"].ok("GET", f"/projects/{ctx['pid']}/coverage")["requirements"]
    assert cov[0]["approvedTestCount"] == 2 and cov[0]["lastResult"] == "FAILED"
