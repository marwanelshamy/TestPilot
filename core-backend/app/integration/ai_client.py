"""C4 L3: AI Service Client — calls the AI Assistance Service (contract I2) over HTTP.

Tactics: timeout (T1), limited retry with backoff (T3), circuit breaker (P9), degradation (T4).
ANY failure (timeout, connection error, 5xx, invalid body, open breaker) becomes AiUnavailable,
which the API turns into 503 AI_UNAVAILABLE while the rest of the core keeps working (QAS-2).
"""

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

import httpx

from app.core.errors import AiUnavailable

log = logging.getLogger(__name__)


class CircuitBreaker:
    """CLOSED -> OPEN after `threshold` consecutive failures; OPEN -> HALF_OPEN after `reset_seconds`;
    one trial call in HALF_OPEN closes it on success or re-opens it on failure."""

    def __init__(self, threshold: int, reset_seconds: float, clock: Callable[[], float] = time.monotonic):
        self.threshold = threshold
        self.reset_seconds = reset_seconds
        self.clock = clock
        self.failures = 0
        self.opened_at: float | None = None
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        if self.opened_at is None:
            return "CLOSED"
        return "HALF_OPEN" if self.clock() - self.opened_at >= self.reset_seconds else "OPEN"

    def allow(self) -> bool:
        return self.state != "OPEN"

    def success(self) -> None:
        with self._lock:
            self.failures = 0
            self.opened_at = None

    def failure(self) -> None:
        with self._lock:
            self.failures += 1
            if self.state == "HALF_OPEN" or self.failures >= self.threshold:
                self.opened_at = self.clock()


class _Retryable(Exception):
    pass


class AiServiceClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        retries: int,
        breaker: CircuitBreaker,
        transport: httpx.BaseTransport | None = None,
        backoff_seconds: float = 0.2,
    ):
        self.retries = retries
        self.breaker = breaker
        self.backoff = backoff_seconds
        self.http = httpx.Client(base_url=base_url, timeout=timeout_seconds, transport=transport)

    # --- public operations (contract I2) ---
    def suggest_tests(self, requirement_text: str, test_types: list[str], code_under_test: str | None) -> dict:
        body = {
            "requirementText": requirement_text,
            "codeUnderTest": code_under_test,
            "language": "python",
            "framework": "pytest",
            "testTypes": test_types,
        }
        data = self._post("/v1/test-suggestions", body)
        suggestions = data.get("suggestions")
        if not isinstance(suggestions, list) or not all(
            isinstance(s, dict) and {"title", "testType", "testCode"} <= s.keys() for s in suggestions
        ):
            self.breaker.failure()
            raise AiUnavailable("AI service returned an invalid response", details={"reason": "INVALID_RESPONSE"})
        return data

    def explain_failure(self, test_code: str, failure_message: str, log_excerpt: str) -> dict:
        data = self._post(
            "/v1/failure-explanations",
            {"testCode": test_code, "failureMessage": failure_message[:4000], "logExcerpt": log_excerpt[:8000]},
        )
        if not isinstance(data.get("explanationText"), str):
            self.breaker.failure()
            raise AiUnavailable("AI service returned an invalid response", details={"reason": "INVALID_RESPONSE"})
        return data

    # --- resilience wrapper ---
    def _post(self, path: str, body: dict) -> dict[str, Any]:
        if not self.breaker.allow():
            raise AiUnavailable(
                "AI assistance is temporarily unavailable. You can still add tests manually.",
                details={"reason": "CIRCUIT_OPEN"},
            )
        last_reason = "UNKNOWN"
        for attempt in range(self.retries + 1):
            try:
                resp = self.http.post(path, json=body)
                if resp.status_code >= 500:
                    raise _Retryable(f"HTTP_{resp.status_code}")
                if resp.status_code >= 400:
                    # a 4xx is our fault, not an outage: do not retry, do not trip the breaker
                    raise AiUnavailable(
                        "AI service rejected the request", details={"reason": f"HTTP_{resp.status_code}"}
                    )
                data = resp.json()
                self.breaker.success()
                return data
            except AiUnavailable:
                raise
            except (httpx.TimeoutException, httpx.TransportError, _Retryable, ValueError) as e:
                last_reason = "TIMEOUT" if isinstance(e, httpx.TimeoutException) else str(e) or type(e).__name__
                log.warning("AI call %s failed (attempt %d): %s", path, attempt + 1, last_reason)
                if attempt < self.retries:
                    time.sleep(self.backoff * (2**attempt))
        self.breaker.failure()
        raise AiUnavailable(
            "AI assistance is temporarily unavailable. You can still add tests manually.",
            details={"reason": last_reason, "circuit": self.breaker.state},
        )
