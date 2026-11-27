# QAS-4 — Modifiability exercise: replace / add the LLM provider (ASR-5)

**Target (M1/M2):** done within **8 developer-hours**, changing **at most 2 production modules**
(configuration and automated tests excluded). **Status:** protocol prepared; executed in Phase 5.

## Change to make

Add a second real provider adapter (e.g. an OpenAI-compatible endpoint such as a local Ollama server, which
is free — C-08) and switch the running system to it **without touching** the Core Backend, database or UI.

## Protocol

1. A team member who did **not** write `ai-service/` performs the change (realistic maintainer).
2. Start from a clean branch: `git checkout -b qas4-exercise <commit>`; record the commit in the log below.
3. Start a timer. Allowed reading: `ai-service/README.md` → "Swapping the LLM provider".
4. Steps expected by the architecture:
   - new module `ai-service/app/providers/<name>_provider.py` implementing `suggest_tests()` and
     `explain_failure()` with `prompts.py`, mapping its errors to `ProviderTimeout` / `ProviderUnavailable` /
     `ProviderBadOutput`;
   - register it in `build_provider()` (`ai-service/app/providers/__init__.py`);
   - `.env`: `LLM_PROVIDER=<name>` (+ URL/key);
   - add adapter tests next to `tests/test_anthropic_provider.py`.
5. Done when: `pytest` in `ai-service` passes, `docker compose up -d --build ai-service` runs, and generating
   tests from the UI returns suggestions with `providerModel` = the new provider.
6. Stop the timer. Record `git diff --stat <start>..HEAD` and classify every changed file.

## Log (fill in)

| Item | Value |
|---|---|
| Person / date | |
| Start commit / end commit | |
| Time spent (h:mm), incl. breaks excluded | |
| Production modules changed (excluding config, tests, docs) | |
| Files changed (`git diff --stat`) | |
| Unexpected changes outside `ai-service/app/providers/` | |
| Verdict (≤ 8 h and ≤ 2 modules?) | MET / NOT MET |
| Interpretation | |
