# AI Assistance Service

Separate container (ASR-2, ASR-5) that turns requirements into candidate pytest tests and explains failed
tests. Contract I2: `docs/contracts/ai-service-api.openapi.yaml`. **No database and no write path to test
status** (ASR-3): suggestions go back to the Core Backend, which stores them as DRAFT for human review.

```
POST /v1/test-suggestions ┐
POST /v1/failure-explanations ┴─> redact + minimise ─> cache ─> circuit breaker ─> rate limit
                                  (P5, C-07)          (T18)    (P9)              (T14)
                              ─> provider adapter ─> validate output ─> response
                                  (P8: mock | anthropic)  (T2)
```

## Modules

| Module | Responsibility | Tactics / patterns |
|---|---|---|
| `app/main.py` | FastAPI routes, request validation, uniform error body | — |
| `app/service.py` | The chain above; maps failures to 502 / 503 / 504 | P9, T1, T4, T14, T18, T21 |
| `app/pipeline/__init__.py` | Pipe-and-filter redaction: secrets → whitespace → length limit | P5, C-07, T8 |
| `app/validation.py` | Drops suggestions that are not valid Python with a `test_*` function or use a wrong type | T2 |
| `app/resilience.py` | Circuit breaker, one-minute rate limiter, TTL response cache | P9, T14, T18 |
| `app/providers/__init__.py` | `LLMProvider` interface + provider-neutral errors + `build_provider()` | P8, T20, T22 |
| `app/providers/prompts.py` | Prompts and JSON schemas shared by every provider | ASR-5 |
| `app/providers/mock_provider.py` | Offline, deterministic, free — the default | C-08 |
| `app/providers/anthropic_provider.py` | Claude adapter: structured outputs, refusal fallback, SDK error mapping | T20, T21 |
| `app/config.py` | Environment settings (provider, model, key, limits) | T24 |

## Configuration (see `../.env.example`)

| Variable | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` | `mock` | `mock` (offline) or `anthropic` |
| `LLM_MODEL` / `LLM_EFFORT` | `claude-opus-5-5` / `medium` | used by the `anthropic` adapter |
| `ANTHROPIC_API_KEY` | — | only in `.env`, never committed |
| `LLM_SEND_CODE` | `false` | C-07: pasted code is sent to an external LLM only when `true` |
| `LLM_TIMEOUT_SECONDS` / `LLM_MAX_RETRIES` | `25` / `1` | worst case ≈ 50 s; Core's `AI_CLIENT_TIMEOUT_SECONDS` (60) must be larger |
| `LLM_BREAKER_FAILURE_THRESHOLD` / `LLM_BREAKER_RESET_SECONDS` | `5` / `30` | circuit breaker |
| `LLM_RATE_LIMIT_PER_MINUTE` | `30` | cost control |
| `LLM_CACHE_TTL_SECONDS` | `3600` | identical redacted requests reuse the last answer |

Error mapping (contract I2): invalid request → `400 VALIDATION_ERROR`; refusal, truncated or invalid
model output → `502 AI_INVALID_OUTPUT`; provider down, breaker open or rate-limited → `503 LLM_UNAVAILABLE`
(`details.reason`); timeout → `504 LLM_TIMEOUT`. The Core Backend shows all of them as `AI_UNAVAILABLE`.

## Run and test

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt
.venv/Scripts/uvicorn --factory app.main:create_app --port 8001     # http://localhost:8001/health
.venv/Scripts/python -m pytest                                       # 29 tests, no network, no key
.venv/Scripts/ruff check app tests
```

| Test file | What it proves |
|---|---|
| `tests/test_pipeline_and_validation.py` | 7 kinds of secrets removed, code kept intact; invalid suggestions dropped |
| `tests/test_api.py` | Responses match contract I2; mock suggestions really run under pytest; 503/504/502 mapping; breaker opens and stops calling the provider; rate limit; cache; secrets and (by default) code never reach an external provider |
| `tests/test_anthropic_provider.py` | Claude request shape (model, JSON-schema output, `fallbacks="default"`); every SDK error class and refusal / truncation mapped |

## Swapping the LLM provider (QAS-4 exercise for Phase 5)

1. Add `app/providers/<name>_provider.py` implementing `suggest_tests()` and `explain_failure()` using
   `prompts.py`, mapping its SDK errors to `ProviderTimeout` / `ProviderUnavailable` / `ProviderBadOutput`.
2. Register it in `build_provider()`.
3. Set `LLM_PROVIDER=<name>` (+ its key) in `.env`.

Nothing in the Core Backend, database or UI changes. Timing this change is the planned QAS-4 evidence.
