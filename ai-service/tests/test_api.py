"""Contract I2 over HTTP: response shapes, error codes, breaker, rate limit, cache and data minimisation."""

import subprocess
import sys
from dataclasses import replace

import jsonschema
from fastapi.testclient import TestClient

from app.main import create_app
from app.providers.mock_provider import MockProvider
from tests.conftest import CODE, contract_response_schema, suggest_body


def test_suggestions_match_contract_and_are_runnable(client, tmp_path):
    r = client.post("/v1/test-suggestions", json=suggest_body(codeUnderTest=CODE))
    assert r.status_code == 200, r.text
    body = r.json()
    jsonschema.validate(body, contract_response_schema("/v1/test-suggestions"))
    assert [s["testType"] for s in body["suggestions"]] == ["NORMAL", "BOUNDARY", "NEGATIVE"]
    assert body["providerModel"] == "fake/fake-1" and body["cached"] is False
    # the mock output is real pytest code: run it
    for i, s in enumerate(body["suggestions"]):
        (tmp_path / f"test_s{i}.py").write_text(s["testCode"], encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(tmp_path)], capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stdout


def test_explanation_matches_contract(client):
    r = client.post(
        "/v1/failure-explanations", json={"testCode": "def test_a(): assert 1 == 2", "failureMessage": "assert 1 == 2"}
    )
    assert r.status_code == 200
    jsonschema.validate(r.json(), contract_response_schema("/v1/failure-explanations"))
    assert r.json()["aiGenerated"] is True and "assert 1 == 2" in r.json()["explanationText"]


def test_bad_requests_are_400(client):
    r = client.post("/v1/test-suggestions", json=suggest_body(language="java"))
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert client.post("/v1/test-suggestions", json=suggest_body(testTypes=["SMOKE"])).status_code == 400


def test_provider_errors_map_to_contract_codes(client, provider):
    for mode, status, code in [
        ("down", 503, "LLM_UNAVAILABLE"),
        ("slow", 504, "LLM_TIMEOUT"),
        ("refuse", 502, "AI_INVALID_OUTPUT"),
    ]:
        provider.mode = mode
        r = client.post("/v1/test-suggestions", json=suggest_body(requirementText=f"req {mode}"))
        assert (r.status_code, r.json()["error"]["code"]) == (status, code), mode
        client.app.state.ai.breaker.success()  # reset between cases


def test_garbage_model_output_is_502_and_never_returned(client, provider):
    provider.payload = {"suggestions": [{"title": "x", "testType": "NORMAL", "testCode": "not python ("}]}
    r = client.post("/v1/test-suggestions", json=suggest_body())
    assert r.status_code == 502 and r.json()["error"]["code"] == "AI_INVALID_OUTPUT"


def test_circuit_breaker_opens_then_answers_without_calling_provider(client, provider):
    provider.mode = "down"
    for i in range(2):  # threshold 2
        assert client.post("/v1/test-suggestions", json=suggest_body(requirementText=f"r{i}")).status_code == 503
    calls = provider.calls
    r = client.post("/v1/test-suggestions", json=suggest_body(requirementText="r3"))
    assert r.status_code == 503 and r.json()["error"]["details"]["reason"] == "CIRCUIT_OPEN"
    assert provider.calls == calls
    assert client.get("/health").json()["llmCircuit"] == "OPEN"


def test_rate_limit(settings, provider):
    c = TestClient(create_app(replace(settings, rate_limit_per_minute=2), provider))
    codes = [c.post("/v1/test-suggestions", json=suggest_body(requirementText=f"q{i}")).status_code for i in range(3)]
    assert codes == [200, 200, 503]


def test_cache_avoids_second_llm_call(client, provider):
    first = client.post("/v1/test-suggestions", json=suggest_body()).json()
    second = client.post("/v1/test-suggestions", json=suggest_body()).json()
    assert provider.calls == 1 and second["cached"] is True and second["suggestions"] == first["suggestions"]
    assert client.get("/health").json()["cache"]["hits"] == 1


def test_secrets_never_reach_the_provider(client, provider):
    leaky = 'add(a, b) returns the sum. Use API_KEY="sk-ant-api03-abcdefghijklmnopqrstuv" for staging.'
    r = client.post("/v1/test-suggestions", json=suggest_body(requirementText=leaky))
    assert r.status_code == 200 and r.json()["redactions"] == 1
    assert "sk-ant-api03" not in provider.seen[-1].requirement_text


def test_code_is_not_sent_to_external_llm_unless_allowed(settings, provider):
    """C-07: an external provider (not the local mock) gets no code unless LLM_SEND_CODE=true."""
    c = TestClient(create_app(settings, provider))
    c.post("/v1/test-suggestions", json=suggest_body(codeUnderTest=CODE))
    assert provider.seen[-1].code_under_test is None
    c2 = TestClient(create_app(replace(settings, send_code_to_llm=True), provider))
    c2.post("/v1/test-suggestions", json=suggest_body(codeUnderTest=CODE, requirementText="other"))
    assert "def add" in provider.seen[-1].code_under_test


def test_default_app_uses_offline_mock():
    c = TestClient(create_app())
    assert c.get("/health").json()["provider"] == "mock"
    assert isinstance(c.app.state.ai.provider, MockProvider)
