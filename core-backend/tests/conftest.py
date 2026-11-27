"""Shared fixtures: a fresh in-memory database per test, a fake AI service and an in-memory publisher."""

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.database import Base, get_engine, session_factory
from app.integration.ai_client import AiServiceClient, CircuitBreaker
from app.integration.job_publisher import InMemoryJobPublisher
from app.main import create_app
from app.repositories import models  # noqa: F401
from app.seed import seed

PASSWORD = "Test#pass1"
REPO_ROOT = Path(__file__).resolve().parents[2]

GOOD_TEST_CODE = "def test_add():\n    assert 1 + 1 == 2\n"


class FakeAi:
    """Programmable stand-in for the AI Assistance Service (contract I2)."""

    def __init__(self):
        self.mode = "ok"  # ok | down | slow | bad
        self.calls = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.mode == "down":
            raise httpx.ConnectError("connection refused", request=request)
        if self.mode == "slow":
            raise httpx.ReadTimeout("timed out", request=request)
        if self.mode == "5xx":
            return httpx.Response(503, json={"error": {"code": "LLM_UNAVAILABLE"}})
        if self.mode == "bad":
            return httpx.Response(200, json={"unexpected": True})
        if request.url.path == "/v1/test-suggestions":
            return httpx.Response(
                200,
                json={
                    "providerModel": "mock/mock-1",
                    "suggestions": [
                        {"title": "adds two positives", "testType": "NORMAL", "testCode": GOOD_TEST_CODE},
                        {
                            "title": "adds zero",
                            "testType": "BOUNDARY",
                            "testCode": "def test_zero():\n    assert 0 + 0 == 0\n",
                        },
                        {"title": "broken suggestion", "testType": "NEGATIVE", "testCode": "def test_x(:\n"},
                    ],
                },
            )
        if request.url.path == "/v1/failure-explanations":
            return httpx.Response(
                200,
                json={
                    "explanationText": "Probably an off-by-one.",
                    "providerModel": "mock/mock-1",
                    "aiGenerated": True,
                },
            )
        return httpx.Response(404)


@pytest.fixture
def settings() -> Settings:
    get_settings.cache_clear()
    return Settings(
        # default: in-memory SQLite; set TEST_DATABASE_URL to run the same suite on PostgreSQL
        database_url=os.environ.get("TEST_DATABASE_URL", "sqlite://"),
        jwt_secret="test-secret-0123456789-0123456789-abcdef",
        ai_service_url="http://ai.test",
        ai_client_retries=1,
        ai_breaker_failure_threshold=2,
        ai_breaker_reset_seconds=60,
        watchdog_enabled=False,
        evidence_max_bytes=200,
        _env_file=None,
    )


@pytest.fixture
def fake_ai() -> FakeAi:
    return FakeAi()


@pytest.fixture
def publisher() -> InMemoryJobPublisher:
    return InMemoryJobPublisher()


@pytest.fixture
def app(settings, fake_ai, publisher, monkeypatch):
    monkeypatch.setattr("app.core.security.get_settings", lambda: settings)
    ai = AiServiceClient(
        settings.ai_service_url,
        1.0,
        settings.ai_client_retries,
        CircuitBreaker(settings.ai_breaker_failure_threshold, settings.ai_breaker_reset_seconds),
        transport=httpx.MockTransport(fake_ai.handler),
        backoff_seconds=0,
    )
    application = create_app(settings=settings, publisher=publisher, ai_client=ai, start_watchdog=False)
    Base.metadata.drop_all(get_engine())
    Base.metadata.create_all(get_engine())
    with session_factory()() as s:
        application.state.user_ids = seed(s, PASSWORD)
    return application


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


@pytest.fixture
def session(app):
    with session_factory()() as s:
        yield s


def login(client: TestClient, who: str) -> dict:
    r = client.post("/api/auth/login", json={"email": f"{who}@testpilot.local", "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
def dev(client):
    return login(client, "dev")


@pytest.fixture
def qa(client):
    return login(client, "qa")


@pytest.fixture
def lead(client):
    return login(client, "lead")


@pytest.fixture
def project_id(client, dev) -> int:
    projects = client.get("/api/projects", headers=dev).json()["items"]
    return next(p["projectId"] for p in projects if p["name"] == "Calculator Demo")


@pytest.fixture
def requirement_id(client, dev, project_id) -> int:
    return client.get(f"/api/projects/{project_id}/requirements", headers=dev).json()["items"][0]["requirementId"]


def make_approved_test(client, dev, project_id, requirement_id, code: str = GOOD_TEST_CODE) -> dict:
    r = client.post(
        f"/api/projects/{project_id}/tests",
        headers=dev,
        json={"title": "t", "testType": "NORMAL", "testCode": code, "requirementIds": [requirement_id]},
    )
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    r = client.post(f"/api/tests/{tid}/approve", headers=dev, json={"version": 1})
    assert r.status_code == 200, r.text
    return r.json()


def message_schema(name: str) -> dict:
    return json.loads((REPO_ROOT / "docs" / "contracts" / "messages" / f"{name}.schema.json").read_text())


def junit(cases: list[tuple[int, int, str]], suite_tests: int | None = None) -> str:
    """cases: (test_case_id, version, 'pass'|'fail'|'error'|'skip')."""
    body = []
    for tc, ver, res in cases:
        inner = {
            "pass": "",
            "fail": '<failure message="assert 3 == 4">AssertionError</failure>',
            "error": '<error message="ImportError">trace</error>',
            "skip": '<skipped message="skip"/>',
        }[res]
        body.append(f'<testcase classname="test_tc_{tc}_v{ver}" name="test_fn" time="0.12">{inner}</testcase>')
    n = len(cases) if suite_tests is None else suite_tests
    suite = f'<testsuite name="pytest" tests="{n}">{"".join(body)}</testsuite>'
    return f'<?xml version="1.0"?><testsuites>{suite}</testsuites>'


def finished(execution_id, **kw) -> dict:
    base = {
        "messageId": str(uuid.uuid4()),
        "schemaVersion": 1,
        "type": "ExecutionFinished",
        "executionId": str(execution_id),
        "workerId": "worker-1",
        "outcome": "COMPLETED",
        "exitCode": 0,
        "junitXml": None,
        "stdout": "collected 1 item\n.",
        "stderr": "",
        "durationMs": 900,
        "sentAt": datetime.now(UTC).isoformat(),
    }
    base.update(kw)
    return base


def heartbeat(execution_id) -> dict:
    return {
        "messageId": str(uuid.uuid4()),
        "schemaVersion": 1,
        "type": "ExecutionHeartbeat",
        "executionId": str(execution_id),
        "workerId": "worker-1",
        "sentAt": datetime.now(UTC).isoformat(),
    }
