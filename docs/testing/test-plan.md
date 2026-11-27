# TestPilot AI — Test Plan and Quality-Evidence Plan (Milestone 3)

**Owner:** Member 5 (Testing + Quality Evidence) · **Status:** prepared in Phase 3; integration tests and
experiments run in Phase 4/5 against the integrated system (`docker compose up --build`).

M3 requires: (§2) measurable evidence for **at least two** quality-attribute scenarios, and (§5) automated unit
tests plus **at least one integration test across component boundaries**, with instructions to run them.
This plan covers **all seven** scenarios; QAS-2, QAS-3 and QAS-7 are the committed minimum, because they
evidence the top ASRs and do not depend on hardware size.

## 1. Test levels

| Level | Where | Tool | Runs without Docker? | Status |
|---|---|---|---|---|
| Unit + component (per container) | `core-backend/tests`, `runner-worker/tests`, `ai-service/tests`, `web-ui/src/test` | pytest, Vitest | yes | **written in Phase 2 — 124 tests** (see §2) |
| Contract (I1, I2, I4) | inside each suite: JSON Schema / OpenAPI checks against `docs/contracts/` | jsonschema, PyYAML | yes | written |
| Architecture conformance | `core-backend/.importlinter`, `tests/unit/test_schema_drift.py` | import-linter, pglast | yes | written |
| Cross-boundary integration (E2E) | `tests/e2e/test_e2e_flow.py` | pytest + httpx | **no** — needs the composed system | **prepared**, run in Phase 4 |
| Quality-attribute experiments | `evidence/qas*/` | Python + httpx (+ `docker compose` for fault injection) | no | **prepared**, run in Phase 5 |
| Usability (formative) | `evidence/qas6_usability/` | task script + observation sheet | n/a | protocol prepared |

## 2. Unit-test inventory (Phase 2, all passing)

| Component (C4) | Suite | Tests | Covers |
|---|---|---|---|
| Core Backend | `core-backend/tests` | 52 | UC-1..UC-4 over HTTP, roles, approval-in-transaction, version-bound approval, report validation (never PASSED without valid evidence), watchdog, idempotent events, AI breaker, schema drift — passes on SQLite **and PostgreSQL** |
| Runner Worker + Sandbox | `runner-worker/tests` | 29 | sandbox isolation options, timeout/OOM/error outcomes, heartbeats, ack/reject/requeue, I4 contract, real pytest report shape |
| AI Assistance Service | `ai-service/tests` | 29 | redaction (7 secret kinds), output validation, 400/502/503/504 mapping, breaker, rate limit, cache, Claude adapter request + error mapping |
| Web UI | `web-ui/src/test` | 14 | API client errors, role matrix, approve-this-version, AI-outage message, run polling stops at terminal state |
| **Total** | | **124** | |

Cross-member checks already done in Phase 2 (not repeatable without the other branch, recorded here as evidence):
real pytest output → Runner Worker message builder → Core report validator (5 cases, incl. `os._exit(0)` fake pass → INTERRUPTED);
live AI service ↔ Core `AiServiceClient` (up and down); Web UI ↔ Core ↔ AI service end-to-end in the browser.

## 3. Quality-attribute evidence matrix

Targets are the proposed response measures from M1/M2 (C-16: not claimed until measured).

| QAS | Attribute / ASR | Stimulus injected | Measured | Pass criterion | Script | Needs |
|---|---|---|---|---|---|---|
| **QAS-3** | Security · ASR-1 | 13 attacks (protected file, Docker socket, internet, PostgreSQL, RabbitMQ, root, secrets in env, write outside /work, fork bomb, memory bomb, fake pass, data left by another project, infinite loop) + 1 control test that must PASS | status of each run; time from start to kill for the 30 s loop | every attack **not PASSED** (blocked or contained); loop killed ≤ 35 s | `evidence/qas3_security/run.py` | compose |
| **QAS-7** | Reliability · ASR-3 | (a) run requests for unapproved / edited tests; (b) Runner Worker killed mid-run; (c) invalid report (fake pass) | rejection rate; final status of crashed runs; detection time | (a) 100 % rejected with 409, no run created; (b) 100 % non-passing terminal state, traceable to execution ID + evidence | `evidence/qas7_reliability/run.py` | (a) backend only; (b, c) compose |
| **QAS-2** | Availability · ASR-2 | AI service stopped for N minutes | success rate of core requests during the outage; latency of the AI error | ≥ 99 % core requests succeed; AI error shown ≤ 3 s after the configured timeout | `evidence/qas2_ai_outage/run.py` | compose |
| **QAS-5** | Scalability · ASR-4 | 100 run requests within 60 s | unique IDs, terminal states, queue wait (`startedAt − createdAt`) | 100 % unique IDs and terminal states; ≥ 95 % start ≤ 30 s at the reported worker capacity | `evidence/qas5_concurrency/run.py` | compose |
| **QAS-1** | Performance (not ASR) | N concurrent users reading latest results of a project with 1,000 tests / 10,000 executions | p95, p99 latency, error rate | p95 ≤ 500 ms, p99 ≤ 1 s | `evidence/qas1_retrieval/seed_results.py` + `load.py` | backend + DB |
| **QAS-4** | Modifiability · ASR-5 | Timed exercise: add a second LLM provider adapter | developer-hours, production modules changed (`git diff --stat`) | ≤ 8 h, ≤ 2 modules | `evidence/qas4_modifiability/exercise.md` | none |
| **QAS-6** | Usability (not ASR) | 10 first-time participants, task script | completion without help, time | ≥ 9/10 unaided, ≥ 9/10 within 5 min | `evidence/qas6_usability/` | UI |

Every script writes a JSON result file and prints a one-line verdict (`MET` / `NOT MET`). `NOT MET` is a valid,
reportable outcome (M3 §2 asks whether the measure is met **or not met**, with interpretation).

## 4. Order of work

1. **Phase 3 (now):** this plan; experiment scripts; E2E test; smoke-test the scripts against a local backend.
2. **Phase 4 (integration):** `docker compose up --build`; run `tests/e2e` → this is the M3 integration test.
3. **Phase 5:** run QAS-3 → QAS-7 → QAS-2 → QAS-5 → QAS-1, store results in `evidence/<qas>/results/`, fill
   `evidence/REPORT-TEMPLATE.md` (method, environment, results, interpretation) for the M3 document.

## 5. Environment to record with every result

Machine (CPU, RAM, OS), Docker version, number of `runner-worker` replicas, `.env` values that matter
(timeouts, limits, `LLM_PROVIDER`), git commit hash, date/time. `evidence/lib/tp.py` records most of this
automatically in each result file.
