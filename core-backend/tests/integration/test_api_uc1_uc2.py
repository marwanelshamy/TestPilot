"""UC-1 (projects + requirements) and UC-2 (generate / review / approve) through the real HTTP API."""

from tests.conftest import GOOD_TEST_CODE


# ---------------- auth & error format ----------------
def test_login_and_me(client, dev):
    me = client.get("/api/me", headers=dev).json()
    assert me["email"] == "dev@testpilot.local" and me["role"] == "DEVELOPER"


def test_wrong_password(client):
    r = client.post("/api/auth/login", json={"email": "dev@testpilot.local", "password": "nope"})
    assert r.status_code == 401
    err = r.json()["error"]
    assert err["code"] == "INVALID_CREDENTIALS" and err["correlationId"]


def test_missing_token_uses_error_body(client):
    r = client.get("/api/projects")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_REQUIRED"


def test_garbage_token(client):
    r = client.get("/api/projects", headers={"Authorization": "Bearer abc.def.ghi"})
    assert r.status_code == 401


def test_validation_error_body(client, dev):
    r = client.post("/api/projects", headers=dev, json={"name": ""})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert r.json()["error"]["details"]["fields"][0]["field"] == "name"


# ---------------- UC-1 ----------------
def test_uc1_create_project_and_requirements(client, dev):
    r = client.post("/api/projects", headers=dev, json={"name": "Shop", "description": "cart"})
    assert r.status_code == 201
    pid = r.json()["id"]
    p = client.get(f"/api/projects/{pid}", headers=dev).json()
    assert (p["programmingLanguage"], p["testFramework"]) == ("Python", "pytest")

    for title in ("cart total", "discount"):
        assert (
            client.post(
                f"/api/projects/{pid}/requirements", headers=dev, json={"title": title, "description": "..."}
            ).status_code
            == 201
        )
    page = client.get(f"/api/projects/{pid}/requirements?size=1", headers=dev).json()
    assert page["total"] == 2 and len(page["items"]) == 1 and page["items"][0]["title"] == "cart total"


def test_uc1_qa_cannot_create_project(client, qa):
    r = client.post("/api/projects", headers=qa, json={"name": "x"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"


def test_uc1_non_member_is_forbidden(client, dev, lead):
    pid = client.post("/api/projects", headers=lead, json={"name": "Lead only"}).json()["id"]
    assert client.get(f"/api/projects/{pid}", headers=dev).status_code == 403
    assert client.get("/api/projects/99999", headers=dev).status_code == 404


# ---------------- UC-2 ----------------
def test_uc2_generate_stores_valid_suggestions_as_draft(client, dev, project_id, requirement_id, fake_ai):
    r = client.post(f"/api/projects/{project_id}/tests/generate", headers=dev, json={"requirementId": requirement_id})
    assert r.status_code == 201, r.text
    ids = r.json()["testIds"]
    assert len(ids) == 2  # the syntactically broken suggestion was dropped (T2)
    t = client.get(f"/api/tests/{ids[0]}", headers=dev).json()
    assert t["status"] == "DRAFT" and t["source"] == "AI_GENERATED" and t["aiGenerated"] is True
    assert t["requirementIds"] == [requirement_id] and t["approvedVersion"] is None


def test_uc2_ai_outage_returns_503_and_core_keeps_working(client, dev, project_id, requirement_id, fake_ai):
    fake_ai.mode = "down"
    r = client.post(f"/api/projects/{project_id}/tests/generate", headers=dev, json={"requirementId": requirement_id})
    assert r.status_code == 503 and r.json()["error"]["code"] == "AI_UNAVAILABLE"
    # QAS-2: unaffected core functions still succeed
    assert client.get(f"/api/projects/{project_id}", headers=dev).status_code == 200
    assert client.get(f"/api/projects/{project_id}/tests", headers=dev).status_code == 200
    r = client.post(
        f"/api/projects/{project_id}/tests",
        headers=dev,
        json={"title": "manual", "testType": "NORMAL", "testCode": GOOD_TEST_CODE},
    )
    assert r.status_code == 201  # manual entry still works (T4 degradation)


def test_uc2_circuit_breaker_stops_calling_a_dead_ai(client, dev, project_id, requirement_id, fake_ai):
    fake_ai.mode = "slow"
    url, body = f"/api/projects/{project_id}/tests/generate", {"requirementId": requirement_id}
    for _ in range(2):  # threshold = 2 in the test settings
        assert client.post(url, headers=dev, json=body).status_code == 503
    calls_before = fake_ai.calls
    r = client.post(url, headers=dev, json=body)
    assert r.status_code == 503 and r.json()["error"]["details"]["reason"] == "CIRCUIT_OPEN"
    assert fake_ai.calls == calls_before  # no network call while the breaker is open
    assert client.get("/api/health").json()["aiCircuit"] == "OPEN"


def test_uc2_invalid_ai_response_is_not_stored(client, dev, project_id, requirement_id, fake_ai):
    fake_ai.mode = "bad"
    r = client.post(f"/api/projects/{project_id}/tests/generate", headers=dev, json={"requirementId": requirement_id})
    assert r.status_code == 503
    assert client.get(f"/api/projects/{project_id}/tests", headers=dev).json()["total"] == 0


def test_uc2_manual_test_must_be_valid_python(client, dev, project_id):
    r = client.post(
        f"/api/projects/{project_id}/tests",
        headers=dev,
        json={"title": "bad", "testType": "NORMAL", "testCode": "print('no test here')"},
    )
    assert r.status_code == 400


def test_uc2_review_edit_approve_flow(client, dev, qa, lead, project_id, requirement_id):
    tid = client.post(
        f"/api/projects/{project_id}/tests",
        headers=qa,
        json={"title": "t", "testType": "BOUNDARY", "testCode": GOOD_TEST_CODE, "requirementIds": [requirement_id]},
    ).json()["id"]

    # QA Assistant is advisory: may edit and flag, may NOT approve (M1 role revision)
    assert client.post(f"/api/tests/{tid}/approve", headers=qa, json={"version": 1}).status_code == 403
    assert (
        client.post(f"/api/tests/{tid}/flags", headers=qa, json={"comment": "add a negative case"}).status_code == 201
    )

    # approve v1 -> edit -> back to DRAFT v2 (ADR-005)
    assert client.post(f"/api/tests/{tid}/approve", headers=lead, json={"version": 1}).json()["status"] == "APPROVED"
    assert client.put(f"/api/tests/{tid}", headers=qa, json={"title": "t2"}).json()["version"] == 2
    t = client.get(f"/api/tests/{tid}", headers=dev).json()
    assert t["status"] == "DRAFT" and t["approvedVersion"] is None

    # approving a stale version is refused
    r = client.post(f"/api/tests/{tid}/approve", headers=dev, json={"version": 1})
    assert r.status_code == 409 and r.json()["error"]["code"] == "VERSION_CONFLICT"
    assert client.post(f"/api/tests/{tid}/approve", headers=dev, json={"version": 2}).json()["approvedVersion"] == 2
    r = client.post(f"/api/tests/{tid}/approve", headers=dev, json={"version": 2})
    assert r.status_code == 409 and r.json()["error"]["code"] == "INVALID_STATE"

    assert client.post(f"/api/tests/{tid}/reject", headers=lead, json={"version": 2}).json()["status"] == "REJECTED"
    assert client.get(f"/api/projects/{project_id}/tests?status=REJECTED", headers=dev).json()["total"] == 1
