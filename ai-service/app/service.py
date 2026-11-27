"""AI assistance use cases. Every LLM call goes through the same chain, in this order:

    redact + minimise (P5, C-07)  ->  cache (T18)  ->  circuit breaker (P9)  ->  rate limit (T14)
    ->  provider adapter (P8)  ->  output validation (T2)  ->  cache store

Errors leave as AiError with the HTTP status of contract I2:
    400 VALIDATION_ERROR · 502 AI_INVALID_OUTPUT · 503 LLM_UNAVAILABLE · 504 LLM_TIMEOUT
"""

import logging
import time
from dataclasses import dataclass

from app.config import AiSettings
from app.pipeline import RedactionPipeline, RedactionReport
from app.providers import (
    ExplainRequest,
    LLMProvider,
    ProviderBadOutput,
    ProviderError,
    ProviderTimeout,
    ProviderUnavailable,
    SuggestRequest,
)
from app.resilience import CircuitBreaker, RateLimiter, TtlCache
from app.validation import InvalidModelOutput, Suggestion, validate_explanation, validate_suggestions

log = logging.getLogger(__name__)


class AiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details or {}


@dataclass
class SuggestResult:
    suggestions: list[Suggestion]
    provider_model: str
    redactions: int
    cached: bool


class AiAssistance:
    def __init__(self, settings: AiSettings, provider: LLMProvider, clock=None):
        clock = clock or time.monotonic
        self.s = settings
        self.provider = provider
        self.pipeline = RedactionPipeline(settings.max_context_chars)
        self.breaker = CircuitBreaker(settings.breaker_failure_threshold, settings.breaker_reset_seconds, clock)
        self.limiter = RateLimiter(settings.rate_limit_per_minute, clock)
        self.cache = TtlCache(settings.cache_ttl_seconds, settings.cache_max_entries, clock)

    @property
    def provider_model(self) -> str:
        return f"{self.provider.name}/{self.provider.model}"

    # ------------------------------------------------------------------ FR-03
    def suggest(self, requirement: str, code: str | None, test_types: list[str], max_suggestions: int) -> SuggestResult:
        report = RedactionReport()
        clean_req = self.pipeline.run(requirement, report)
        # C-07: source code only leaves the system for an external provider when explicitly allowed
        send_code = code if (self.provider.name == "mock" or self.s.send_code_to_llm) else None
        clean_code = self.pipeline.run(send_code, report)
        n = min(max_suggestions, self.s.max_suggestions)
        req = SuggestRequest(clean_req, clean_code, list(test_types), n)

        key = TtlCache.key("suggest", self.provider_model, req.requirement_text, req.code_under_test, req.test_types, n)
        if (hit := self.cache.get(key)) is not None:
            return SuggestResult(hit, self.provider_model, report.secrets_removed, cached=True)

        raw = self._call(lambda: self.provider.suggest_tests(req))
        try:
            suggestions = validate_suggestions(raw, req.test_types, n)
        except InvalidModelOutput as e:
            self.breaker.failure()  # a provider that keeps returning garbage is also "failing"
            raise AiError(502, "AI_INVALID_OUTPUT", str(e)) from e
        self.cache.put(key, suggestions)
        return SuggestResult(suggestions, self.provider_model, report.secrets_removed, cached=False)

    # ------------------------------------------------------------------ FR-09
    def explain(self, test_code: str, failure_message: str, log_excerpt: str) -> str:
        report = RedactionReport()
        req = ExplainRequest(
            self.pipeline.run(test_code, report) or "",
            self.pipeline.run(failure_message, report) or "",
            self.pipeline.run(log_excerpt, report) or "",
        )
        key = TtlCache.key("explain", self.provider_model, req.test_code, req.failure_message, req.log_excerpt)
        if (hit := self.cache.get(key)) is not None:
            return hit
        raw = self._call(lambda: self.provider.explain_failure(req))
        try:
            text = validate_explanation(raw)
        except InvalidModelOutput as e:
            self.breaker.failure()
            raise AiError(502, "AI_INVALID_OUTPUT", str(e)) from e
        self.cache.put(key, text)
        return text

    # ------------------------------------------------------------------ guarded provider call
    def _call(self, fn):
        if not self.breaker.allow():
            raise AiError(503, "LLM_UNAVAILABLE", "LLM provider is temporarily unavailable", {"reason": "CIRCUIT_OPEN"})
        if not self.limiter.try_acquire():
            raise AiError(503, "LLM_UNAVAILABLE", "LLM request rate limit reached", {"reason": "RATE_LIMITED"})
        try:
            result = fn()
        except ProviderTimeout as e:
            self.breaker.failure()
            raise AiError(504, "LLM_TIMEOUT", str(e), {"reason": e.reason}) from e
        except ProviderUnavailable as e:
            self.breaker.failure()
            raise AiError(503, "LLM_UNAVAILABLE", str(e), {"reason": e.reason}) from e
        except ProviderBadOutput as e:
            self.breaker.failure()
            raise AiError(502, "AI_INVALID_OUTPUT", str(e), {"reason": e.reason}) from e
        except ProviderError as e:  # e.g. our request was rejected: not an outage, do not trip the breaker
            log.error("LLM request rejected: %s", e)
            raise AiError(502, "AI_INVALID_OUTPUT", str(e), {"reason": e.reason}) from e
        self.breaker.success()
        return result
