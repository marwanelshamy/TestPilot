# ADR-016: Timeout hierarchy: every outer timeout is longer than the inner one

| Field | Content |
|---|---|
| ADR number & title | ADR-016: Timeout hierarchy: every outer timeout is longer than the inner one |
| Status | Accepted |
| Date & deciders | 27 November 2026 - Member 3 with Member 1 (Phases 2 and 4) |
| Context | M1/M2 assumed a 10 s AI timeout. The AI service itself waits for the LLM (25 s per attempt, up to 2 attempts, about 50 s); if the Core Backend gave up first, the user would get a timeout although the answer was on its way, and the AI service would keep working for nothing. |
| Alternatives considered | 1. Keep 10 s everywhere: fast failures, but realistic LLM calls fail.<br>2. Strict hierarchy Nginx 90 s > Core AI client 60 s > AI service worst case about 50 s > LLM attempt 25 s (chosen). |
| Decision | Values in `.env.example` (`AI_CLIENT_TIMEOUT_SECONDS=60`, `LLM_TIMEOUT_SECONDS=25`, `LLM_MAX_RETRIES=1`) and `web-ui/nginx.conf` (`proxy_read_timeout 90s`). |
| Rationale | Every layer returns a clear error before the layer above it gives up. |
| Consequences | + Once open, the circuit breaker still answers in milliseconds (QAS-2: max 0.08 s). - A hanging provider can hold a request for up to 60 s before the breaker opens (not injected in QAS-2; recorded as a limit). |
