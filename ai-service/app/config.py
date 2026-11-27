"""AI service settings from environment variables (T24: provider, model and key come from configuration,
never from the repository — C-08). This service has NO database settings (ASR-3)."""

import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class AiSettings:
    # Provider adapter (P8, ASR-5): "mock" (offline, default) or "anthropic"
    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "mock").strip().lower())
    llm_model: str = field(default_factory=lambda: _env("LLM_MODEL", "").strip() or "claude-opus-5-5")
    llm_effort: str = field(default_factory=lambda: _env("LLM_EFFORT", "medium"))
    llm_max_tokens: int = field(default_factory=lambda: int(_env("LLM_MAX_TOKENS", "16000")))
    # Per-attempt timeout and SDK retries. Worst case ≈ timeout × (retries + 1); keep it BELOW the
    # Core Backend's AI_CLIENT_TIMEOUT_SECONDS so the core never gives up first.
    llm_timeout_seconds: float = field(default_factory=lambda: float(_env("LLM_TIMEOUT_SECONDS", "25")))
    llm_max_retries: int = field(default_factory=lambda: int(_env("LLM_MAX_RETRIES", "1")))

    # Circuit breaker on the LLM call (P9)
    breaker_failure_threshold: int = field(default_factory=lambda: int(_env("LLM_BREAKER_FAILURE_THRESHOLD", "5")))
    breaker_reset_seconds: float = field(default_factory=lambda: float(_env("LLM_BREAKER_RESET_SECONDS", "30")))

    # Cost control (C-08): rate limit (T14) and response cache (T18)
    rate_limit_per_minute: int = field(default_factory=lambda: int(_env("LLM_RATE_LIMIT_PER_MINUTE", "30")))
    cache_ttl_seconds: float = field(default_factory=lambda: float(_env("LLM_CACHE_TTL_SECONDS", "3600")))
    cache_max_entries: int = field(default_factory=lambda: int(_env("LLM_CACHE_MAX_ENTRIES", "256")))

    # Data minimisation (C-07): code is only sent to an external LLM when explicitly allowed
    send_code_to_llm: bool = field(default_factory=lambda: _env("LLM_SEND_CODE", "false").lower() == "true")
    max_context_chars: int = field(default_factory=lambda: int(_env("LLM_MAX_CONTEXT_CHARS", "12000")))
    max_suggestions: int = field(default_factory=lambda: int(_env("LLM_MAX_SUGGESTIONS", "5")))
