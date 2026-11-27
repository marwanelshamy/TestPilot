"""Provider adapter interface (pattern P8, tactic T20, ASR-5 / QAS-4).

The rest of the service only knows `LLMProvider` and the four error types below. Replacing the LLM
provider = writing one new adapter module + registering it in `build_provider()` + configuration.
"""

from dataclasses import dataclass
from typing import Protocol


# ---------------------------------------------------------------- requests (already redacted)
@dataclass(frozen=True)
class SuggestRequest:
    requirement_text: str
    code_under_test: str | None
    test_types: list[str]
    max_suggestions: int


@dataclass(frozen=True)
class ExplainRequest:
    test_code: str
    failure_message: str
    log_excerpt: str


# ---------------------------------------------------------------- errors every adapter maps to
class ProviderError(Exception):
    """Base class. `reason` is a short machine string used in logs and error details."""

    reason = "PROVIDER_ERROR"

    def __init__(self, message: str, reason: str | None = None):
        super().__init__(message)
        if reason:
            self.reason = reason


class ProviderUnavailable(ProviderError):  # outage, 5xx, connection error, rate limited -> 503
    reason = "UNAVAILABLE"


class ProviderTimeout(ProviderError):  # no answer in time -> 504
    reason = "TIMEOUT"


class ProviderBadOutput(ProviderError):  # refusal, truncated or unparseable output -> 502
    reason = "BAD_OUTPUT"


class LLMProvider(Protocol):
    name: str
    model: str

    def suggest_tests(self, req: SuggestRequest) -> dict:
        """Return {"suggestions": [{"title", "description", "testType", "testCode"}, ...]}."""

    def explain_failure(self, req: ExplainRequest) -> dict:
        """Return {"explanationText": str}."""


def build_provider(settings) -> LLMProvider:
    if settings.llm_provider == "mock":
        from app.providers.mock_provider import MockProvider

        return MockProvider()
    if settings.llm_provider == "anthropic":
        from app.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider(settings)
    raise ValueError(f"Unknown LLM_PROVIDER={settings.llm_provider!r} (supported: mock, anthropic)")
