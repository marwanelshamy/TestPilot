"""The Claude adapter, with the SDK client replaced by a fake (no network, no key, no cost).

Checks the request it builds (model, structured output schema, refusal fallback) and that every SDK
error class maps to the provider-neutral error the service understands."""

import json
from dataclasses import replace
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from app.config import AiSettings
from app.providers import (
    ExplainRequest,
    ProviderBadOutput,
    ProviderError,
    ProviderTimeout,
    ProviderUnavailable,
    SuggestRequest,
)
from app.providers.anthropic_provider import FALLBACK_BETA, AnthropicProvider
from app.providers.prompts import SUGGESTIONS_SCHEMA

REQ = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def status_error(cls, code):
    return cls(f"HTTP {code}", response=httpx2.Response(code, request=REQ), body=None)


class FakeMessages:
    def __init__(self, outcome):
        self.outcome = outcome
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def reply(text=None, stop_reason="end_turn", category=None):
    content = [SimpleNamespace(type="text", text=text)] if text is not None else []
    details = SimpleNamespace(category=category) if stop_reason == "refusal" else None
    return SimpleNamespace(content=content, stop_reason=stop_reason, stop_details=details)


def make(outcome):
    fake = FakeMessages(outcome)
    client = SimpleNamespace(beta=SimpleNamespace(messages=fake))
    settings = replace(AiSettings(), llm_provider="anthropic", llm_model="claude-opus-5-5", llm_effort="medium")
    return AnthropicProvider(settings, client=client), fake


SUGGEST = SuggestRequest("add returns the sum", None, ["NORMAL"], 3)


def test_builds_a_structured_output_request_with_fallback():
    payload = {
        "suggestions": [{"title": "t", "description": "d", "testType": "NORMAL", "testCode": "def test_a(): pass"}]
    }
    provider, fake = make(reply(json.dumps(payload)))
    assert provider.suggest_tests(SUGGEST) == payload
    k = fake.kwargs
    assert k["model"] == "claude-opus-5-5"
    assert k["output_config"] == {"effort": "medium", "format": {"type": "json_schema", "schema": SUGGESTIONS_SCHEMA}}
    assert k["betas"] == [FALLBACK_BETA] and k["fallbacks"] == "default"
    assert "add returns the sum" in k["messages"][0]["content"] and "pytest" in k["system"]


def test_explanation_request():
    provider, fake = make(reply(json.dumps({"explanationText": "Off by one."})))
    out = provider.explain_failure(ExplainRequest("def test_a(): assert f(1) == 2", "assert 1 == 2", "log"))
    assert out == {"explanationText": "Off by one."} and "hypothesis" in fake.kwargs["system"]


@pytest.mark.parametrize(
    "error, expected, reason",
    [
        (anthropic.APITimeoutError(request=REQ), ProviderTimeout, "TIMEOUT"),
        (anthropic.APIConnectionError(request=REQ), ProviderUnavailable, "CONNECTION"),
        (status_error(anthropic.RateLimitError, 429), ProviderUnavailable, "RATE_LIMITED"),
        (status_error(anthropic.AuthenticationError, 401), ProviderUnavailable, "AUTH"),
        (status_error(anthropic.InternalServerError, 500), ProviderUnavailable, "HTTP_500"),
        (status_error(anthropic.APIStatusError, 529), ProviderUnavailable, "HTTP_529"),
        (status_error(anthropic.BadRequestError, 400), ProviderError, "BAD_REQUEST"),
    ],
)
def test_sdk_errors_map_to_provider_errors(error, expected, reason):
    provider, _ = make(error)
    with pytest.raises(expected) as exc:
        provider.suggest_tests(SUGGEST)
    assert exc.value.reason == reason


@pytest.mark.parametrize(
    "response, reason",
    [
        (reply(stop_reason="refusal", category="cyber"), "REFUSAL"),
        (reply('{"suggestions": [', stop_reason="max_tokens"), "TRUNCATED"),
        (reply(None), "NO_TEXT"),
        (reply("not json"), "INVALID_JSON"),
    ],
)
def test_bad_responses_are_bad_output(response, reason):
    provider, _ = make(response)
    with pytest.raises(ProviderBadOutput) as exc:
        provider.suggest_tests(SUGGEST)
    assert exc.value.reason == reason
