# ADR-018: Database session lifecycle, explicit pool sizing and admission control

| Field | Content |
|---|---|
| ADR number & title | ADR-018: Database session lifecycle, explicit pool sizing and admission control |
| Status | Accepted |
| Date & deciders | 27 November 2026 - Member 1 with Member 5 (found by the QAS-1 load test, Phase 5) |
| Context | QAS-1 (200 concurrent users) deadlocked the Core Backend: all 40 API worker threads waited for a database connection while every connection was held by a finished request waiting for a worker thread to serialise its response; cancelled requests also leaked connections (evidence: `evidence/qas1_retrieval/results/run2-pyspy-thread-dump.txt`). The backend stayed hung after the load stopped: an availability failure, not only a performance one. |
| Alternatives considered | 1. A bigger connection pool only: tried in run 2, the deadlock came back with the larger pool.<br>2. Rewrite the core fully async (async SQLAlchemy): removes the thread pool, but a large change late in the milestone.<br>3. Async session dependency (clean-up on the event loop) + explicit pool (20 + 10, 10 s timeout, exhaustion answered with `503 SERVICE_BUSY`) + admission control: at most 25 requests in flight, FIFO wait on the event loop, 503 after 5 s, `/api/health` exempt (chosen). |
| Decision | `app/core/database.py` (async `get_session`, pool sizing), `app/api/errors.py` (503 SERVICE_BUSY), new middleware `app/api/admission.py`; limits are configurable (`MAX_INFLIGHT_REQUESTS`, `ADMISSION_WAIT_SECONDS`, `DB_POOL_*`). |
| Rationale | Admission control keeps in-flight work below both the thread pool and the connection pool, so a finishing request always gets a thread and returns its connection; overload becomes fast, explicit 503s instead of a hang (new tactic: bound concurrency / bound queue size). |
| Consequences | + Run 3: 69,264 requests, 0.18 % errors, health answering throughout, no stuck connections (run 1: 96.6 % errors and a hung backend). + 10 regression tests. - Under overload some requests get 503 (availability over latency). - QAS-1 latency still NOT MET (p95 1.37 s): one process serves about 77 req/s. Follow-up: more Core Backend processes or replicas, a short-lived cache for the latest-results page. |
