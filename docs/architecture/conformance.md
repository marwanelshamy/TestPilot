# Architecture Conformance (M3 §3) — Phase 4 review

**Reviewer:** Member 4 · **Code reviewed:** branch `integration/phase4` (all member branches merged).
**Result:** the code follows the M2 views. Every container and Core Backend component maps to code;
every "deliberately missing link" is absent and **guarded by an automated test**; 12 deviations are recorded
below as design changes (to be written up as ADR-009/ADR-010 in the M3 document).

## 1. Container view (C4 L2) → code and deployment

| Container (M2 §3.1) | Code | Image / compose service | Technology as built |
|---|---|---|---|
| Web UI | `web-ui/` | `web-ui` (Nginx, port 8080) | React 19 + TypeScript + Vite, Nginx 1.27 |
| Core Backend | `core-backend/app/` | `core-backend` (internal) | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, pika |
| AI Assistance Service | `ai-service/app/` | `ai-service` (internal + egress) | FastAPI, provider adapters (mock, Claude) |
| Message Broker | `core-backend/app/integration/amqp_topology.py` = `runner-worker/worker/topology.py` | `rabbitmq` | RabbitMQ 3.13, quorum queues + DLQs |
| Runner Worker | `runner-worker/worker/` | `runner-worker` ×2 | Python, aio-pika, Docker SDK |
| Test Sandbox | `sandbox-image/` | built by `sandbox-image`, started per run | python:3.12-slim + pytest, non-root |
| Database | `db/schema.sql` = `core-backend/app/repositories/models.py` | `postgres` | PostgreSQL 16 |

Links R1–R10 as built: R1/R2 Nginx → `core-backend:8000` (only upstream); R3 `app/integration/ai_client.py`;
R4 `ai-service/app/providers/*`; R5 `app/integration/amqp_publisher.py`; R6/R7 `runner-worker/worker/main.py`;
R8 `app/api/listeners/execution_events.py`; R9 `app/repositories/*`; R10 `runner-worker/worker/sandbox.py`.
R11 (GitHub) is not built (FR-14 Could).

## 2. Component view (C4 L3, Core Backend) → modules

| Component | Module | Layer |
|---|---|---|
| Auth & Access Filter | `app/api/deps/auth.py` (+ `services/auth_service.py`, `repositories/user_repository.py`) | API |
| Project API · Test Case & Approval API · Execution & Results API | `app/api/routers/projects.py` · `tests.py` · `executions.py` | API |
| Execution Event Listener | `app/api/listeners/execution_events.py` | API (inbound adapter) |
| Project Service · Test Case & Approval Service · Results & Reporting Service | `app/services/project_service.py` · `test_case_service.py` · `results_service.py` | Business |
| Execution Orchestrator | `app/services/orchestrator/` (`__init__`, `state_machine`, `report_validator`, `watchdog`) | Business |
| Project / Test Case / Results / Execution Repository | `app/repositories/*_repository.py` | Data access |
| AI Service Client · Job Publisher | `app/integration/ai_client.py` · `job_publisher.py` (port) + `amqp_publisher.py` (adapter) | Integration |

## 3. How erosion is prevented (automated)

| Rule from the design | Guard | Where |
|---|---|---|
| Closed layers API → services → repositories/integration | import-linter contract `layers` | `core-backend/.importlinter` |
| Only the orchestrator writes execution status (ASR-3) | import-linter contract `status-writer` + DB CHECK constraints | `.importlinter`, `db/schema.sql` |
| Integration adapters never touch the DB | import-linter contract `no-db-in-integration` | `.importlinter` |
| Data model = agreed contract | schema-drift test (ORM vs `db/schema.sql`) | `core-backend/tests/unit/test_schema_drift.py` |
| Contracts I1/I2/I4 honoured by both sides | JSON-Schema / OpenAPI contract tests in each service | each `tests/` |
| Both AMQP clients declare identical queues | topology equality test | `core-backend/tests/unit/test_amqp.py` |
| Only the core has DB credentials; sandbox has no network; only UI/broker console publish ports; only AI service has egress; Docker socket only in the runner; ≥ 2 workers | compose rules | `tests/architecture/test_architecture_rules.py` |
| Runner/AI service never import DB libraries; runner never decides PASSED; AI has no path to status; UI talks only to `/api`; Python + pytest only | code rules | `tests/architecture/test_architecture_rules.py` |

Run all guards: `core-backend: lint-imports && pytest` · repo root: `python -m pytest tests/architecture`.

## 4. Deviations from the M2 design (→ ADR-009 / ADR-010)

| # | M2 said | As built | Why | Impact |
|---|---|---|---|---|
| 1 | Endpoints of M2 §4.2 | + manual test entry, `GET /projects`, `/me`, `/projects/{id}/executions` | manual entry during AI outage (M2 §3.2), UI lists | additive |
| 2 | Approve a test | approve **with the reviewed version**, `409 VERSION_CONFLICT` | makes ADR-005 enforceable over HTTP | additive |
| 3 | — | `503 QUEUE_UNAVAILABLE`, insert rolled back | no orphan QUEUED row | additive |
| 4 | reasons in prose | enums `INVALID_REPORT`, `RESOURCE_LIMIT`, `INTERNAL_ERROR`; outcome `RESOURCE_LIMIT` | needed in data + messages | additive |
| 5 | 14 entities | 13 entities + `processed_message`; `time_limit_seconds`, `truncated` columns; CHECK constraints | idempotent events (R-011), watchdog, OI-008, defence in depth | additive |
| 6 | durable queues | **quorum** queues, `x-delivery-limit=3`, DLQs | a crash-looping job ends in the DLQ, not an endless loop | changes broker config |
| 7 | Auth filter checks membership | filter checks token + role; **business layer** checks membership | membership needs data; keeps the API layer free of repositories | moves a check one layer down |
| 8 | AMQP in core with aio-pika | **pika** (sync) with publisher confirms; listener in a background thread | core endpoints are synchronous; avoids a second event loop | technology only |
| 9 | Report = "valid JUnit XML" | valid **and** covers every requested test **and** exit code consistent with failures | blocks partial / forged reports (QAS-7) | stricter |
| 10 | Sandbox read-only FS + scratch folder | read-only root FS, `/work` anonymous volume, `/tmp` tmpfs noexec, `cap_drop ALL`, `pids_limit` | Docker only allows copying files into a volume of a read-only container | stricter |
| 11 | provider undecided (OI-003) | offline **mock** default + **Claude** adapter; code sent to an external LLM only with `LLM_SEND_CODE=true` | free/offline demo (C-08), privacy (C-07) | OI-003 partly closed |
| 12 | AI timeout 10 s | core waits 60 s; AI service worst case 50 s; Nginx 90 s | each outer timeout must exceed the inner one | config |

No container, boundary, style, ASR or pattern was removed or added.

## 5. Open findings (not blocking Phase 4)

1. **R-009** — the Runner Worker holds the Docker socket. Mitigation proposal: a socket proxy that only allows
   container create/start/kill/remove/archive.
2. A test file that cannot be imported makes pytest exit 2 → `INTERRUPTED / INVALID_REPORT` (never passed,
   but less helpful than "ERROR in test N"). Possible improvement of the report validator.
3. A user test can fake its own pass from inside the test process (e.g. write a fake report, then exit 0) only if
   it reproduces pytest's report exactly; the validator's exit-code and completeness checks block the
   simple variants (`os._exit(0)` → INTERRUPTED). Inherent limit: tests are the user's own code. Record in ATAM.
4. Project membership has no management UI (FR-13 is future work): only a project's creator is a member.
