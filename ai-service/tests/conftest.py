from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.config import AiSettings
from app.main import create_app
from app.providers import ProviderBadOutput, ProviderTimeout, ProviderUnavailable
from app.providers.mock_provider import MockProvider

REPO_ROOT = Path(__file__).resolve().parents[2]
CODE = "def add(a, b):\n    return a + b\n"


def contract_response_schema(path: str) -> dict:
    spec = yaml.safe_load(
        (REPO_ROOT / "docs" / "contracts" / "ai-service-api.openapi.yaml").read_text(encoding="utf-8")
    )
    return spec["paths"][path]["post"]["responses"]["200"]["content"]["application/json"]["schema"]


class FakeProvider(MockProvider):
    """MockProvider whose behaviour the test controls; records exactly what would leave the system."""

    name = "fake"
    model = "fake-1"

    def __init__(self):
        self.mode = "ok"
        self.calls = 0
        self.seen: list = []
        self.payload = None

    def _maybe_fail(self):
        self.calls += 1
        if self.mode == "down":
            raise ProviderUnavailable("provider down")
        if self.mode == "slow":
            raise ProviderTimeout("too slow")
        if self.mode == "refuse":
            raise ProviderBadOutput("declined", reason="REFUSAL")

    def suggest_tests(self, req):
        self._maybe_fail()
        self.seen.append(req)
        return self.payload if self.payload is not None else super().suggest_tests(req)

    def explain_failure(self, req):
        self._maybe_fail()
        self.seen.append(req)
        return self.payload if self.payload is not None else super().explain_failure(req)


@pytest.fixture
def settings() -> AiSettings:
    return replace(
        AiSettings(),
        llm_provider="fake",
        breaker_failure_threshold=2,
        breaker_reset_seconds=60,
        rate_limit_per_minute=100,
        send_code_to_llm=False,
    )


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def client(settings, provider) -> TestClient:
    return TestClient(create_app(settings, provider))


def suggest_body(**kw) -> dict:
    body = {"requirementText": "add(a, b) returns the sum", "language": "python", "framework": "pytest"}
    body.update(kw)
    return body
