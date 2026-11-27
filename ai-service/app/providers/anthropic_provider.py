"""Anthropic (Claude) adapter. Selected with LLM_PROVIDER=anthropic; key from ANTHROPIC_API_KEY (never committed).

* Model from LLM_MODEL, default `claude-opus-5-5`; effort from LLM_EFFORT (default `medium`).
* Structured outputs (`output_config.format` = JSON Schema) so the reply is guaranteed-valid JSON.
* Server-side refusal fallback (`fallbacks="default"`, beta `server-side-fallback-2026-07-01`): if the model
  declines for policy reasons, the API retries on its default fallback model inside the same call.
* SDK timeout + retries come from configuration; every SDK error is mapped to the provider-neutral errors.
"""

import json
import logging

import anthropic

from app.config import AiSettings
from app.providers import (
    ExplainRequest,
    ProviderBadOutput,
    ProviderError,
    ProviderTimeout,
    ProviderUnavailable,
    SuggestRequest,
)
from app.providers.prompts import (
    EXPLAIN_SYSTEM,
    EXPLANATION_SCHEMA,
    SUGGEST_SYSTEM,
    SUGGESTIONS_SCHEMA,
    explain_user_prompt,
    suggest_user_prompt,
)

log = logging.getLogger(__name__)

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, settings: AiSettings, client: anthropic.Anthropic | None = None):
        self.s = settings
        self.model = settings.llm_model
        # Zero-arg style: credentials resolve from the environment (ANTHROPIC_API_KEY or an `ant auth login` profile)
        self.client = client or anthropic.Anthropic(
            timeout=settings.llm_timeout_seconds, max_retries=settings.llm_max_retries
        )

    # ------------------------------------------------------------------ operations
    def suggest_tests(self, req: SuggestRequest) -> dict:
        prompt = suggest_user_prompt(req.requirement_text, req.code_under_test, req.test_types, req.max_suggestions)
        return self._json_call(SUGGEST_SYSTEM, prompt, SUGGESTIONS_SCHEMA)

    def explain_failure(self, req: ExplainRequest) -> dict:
        prompt = explain_user_prompt(req.test_code, req.failure_message, req.log_excerpt)
        return self._json_call(EXPLAIN_SYSTEM, prompt, EXPLANATION_SCHEMA)

    # ------------------------------------------------------------------ one structured call
    def _json_call(self, system: str, user: str, schema: dict) -> dict:
        try:
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=self.s.llm_max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"effort": self.s.llm_effort, "format": {"type": "json_schema", "schema": schema}},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except anthropic.APITimeoutError as e:  # subclass of APIConnectionError: catch it first
            raise ProviderTimeout("LLM did not answer in time") from e
        except anthropic.RateLimitError as e:
            raise ProviderUnavailable("LLM rate limit reached", reason="RATE_LIMITED") from e
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
            raise ProviderUnavailable("LLM credentials rejected", reason="AUTH") from e
        except anthropic.BadRequestError as e:
            raise ProviderError(f"LLM rejected the request: {e.message}", reason="BAD_REQUEST") from e
        except anthropic.APIStatusError as e:
            raise ProviderUnavailable(f"LLM error HTTP {e.status_code}", reason=f"HTTP_{e.status_code}") from e
        except anthropic.APIConnectionError as e:
            raise ProviderUnavailable("cannot reach the LLM provider", reason="CONNECTION") from e

        if response.stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None) if response.stop_details else None
            raise ProviderBadOutput(f"LLM declined the request (category={category})", reason="REFUSAL")
        if response.stop_reason == "max_tokens":
            raise ProviderBadOutput("LLM output was cut off at max_tokens", reason="TRUNCATED")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise ProviderBadOutput("LLM returned no text block", reason="NO_TEXT")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ProviderBadOutput("LLM returned invalid JSON", reason="INVALID_JSON") from e
