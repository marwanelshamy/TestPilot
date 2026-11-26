# Phase 1 — Locked Architecture and Technologies

**Status:** Locked for M3. Any change after this point needs a new ADR (ADR-009+) in `docs/adr/`.
**Source:** M2 SAD §2.4 (style), §3.1 (containers), §3.2 (components), ADR-001…ADR-008.

## 1. Architecture (unchanged from M2)

- **Style:** Layered Core Backend + event-driven test execution (ADR-001).
- **Communication:** HTTPS/REST + JSON for request/reply (R1–R4, R9); AMQP via RabbitMQ for execution (R5–R8) (ADR-002).
- **Single writer:** only the Execution Orchestrator in the Core Backend writes execution status (ADR-004, ADR-006).
- **Isolation:** trusted Runner Worker starts one short-lived Test Sandbox container per run (ADR-003).
- **Deliberately missing links** (must stay missing in code): Runner/Sandbox → DB, AI Service → DB, Sandbox → network, Web UI → AI Service or broker.

```
 Users ──HTTPS──> web-ui (Nginx + React) ──/api──> core-backend (FastAPI) ──SQL──> postgres
                                                     │  │
                                    HTTP (internal)  │  │ AMQP  execution.requests / execution.events
                                                     v  v
                                          ai-service   rabbitmq <──AMQP── runner-worker ──Docker API──> test-sandbox (per run)
                                              │
                                        LLM provider (adapter: mock | real)
```

## 2. Containers → repository folders → technology

| Container (M2 §3.1) | Folder | Technology (locked) | Port (dev) |
|---|---|---|---|
| Web UI | `web-ui/` | React 18 + TypeScript + Vite, built to static files, served by Nginx 1.27 (also reverse-proxies `/api`) | 8080 |
| Core Backend | `core-backend/` | Python 3.12, FastAPI, SQLAlchemy 2 (ORM), Pydantic 2, Alembic (migrations), aio-pika (AMQP), httpx (AI client), PyJWT, bcrypt | 8000 (internal) |
| AI Assistance Service | `ai-service/` | Python 3.12, FastAPI, httpx, tenacity (retry), circuit breaker in-house or `pybreaker`; adapters `mock` and one hosted LLM | 8001 (internal) |
| Message Broker | (image only) | RabbitMQ 3.13 with management plugin | 5672, 15672 |
| Runner Worker | `runner-worker/` | Python 3.12, aio-pika, Docker SDK for Python 7 | — |
| Test Sandbox | `sandbox-image/` | `python:3.12-slim` + pytest 8, non-root user | — |
| Database | `core-backend/migrations` + `db/schema.sql` | PostgreSQL 16 | 5432 |
| Orchestration | `docker-compose.yml` | Docker Compose v2 — **one command: `docker compose up --build`** | — |

## 3. Cross-cutting choices

| Topic | Decision |
|---|---|
| Language/framework under test | Python + pytest only (C-01, ADR-007, OI-001 now **confirmed** for M3) |
| Auth | Simple login → JWT (HS256), 60 min expiry; roles DEVELOPER, QA_ASSISTANT, TEAM_LEAD, ADMIN (A-04) |
| LLM provider | Adapter interface with **`mock` as default** (works offline, used in tests and demo). A real provider adapter is added in Phase 2; which one is still OI-003. Keys only in `.env`, never committed (C-08, T24). |
| AI call resilience | Core → AI: timeout 10 s, 2 retries with backoff, breaker opens after 5 consecutive failures for 30 s. AI → LLM: timeout 20 s. *(Starting values, tuned in Phase 3.)* |
| Execution limits | Default per run: 30 s time, 1 CPU, 256 MB memory, `network_mode=none`, read-only root FS + tmpfs `/tmp`, user `sandbox` (QAS-3) |
| Heartbeat / watchdog (OI-007) | Heartbeat every 5 s; run marked INTERRUPTED (RUNNER_LOST) after 3 missed heartbeats (15 s) — **proposed**, confirmed in Phase 3 |
| Log cap (OI-008) | 64 KB per evidence row, truncated with a marker — **proposed** |
| Status delivery to UI | Polling `GET /api/executions/{id}` every 2 s (A-05) |
| Error body | `{ "error": { code, message, details, correlationId } }` on every non-2xx (M2 §4.5) |
| Layer enforcement | `import-linter` contracts in `core-backend/.importlinter` (API → services → repositories/integration; never upward) |
| Tests | pytest (unit + integration), Vitest for the UI (optional), k6 or Locust for load (Phase 3) |
| Style/lint | ruff (Python), ESLint + Prettier (TS) |

## 4. Core Backend package layout (maps C4 L3 components → modules)

| C4 L3 component | Module |
|---|---|
| Auth & Access Filter | `app/api/deps/auth.py` |
| Project API | `app/api/routers/projects.py` |
| Test Case & Approval API | `app/api/routers/tests.py` |
| Execution & Results API | `app/api/routers/executions.py` |
| Execution Event Listener | `app/api/listeners/execution_events.py` |
| Project Service | `app/services/project_service.py` |
| Test Case & Approval Service | `app/services/test_case_service.py` |
| Results & Reporting Service | `app/services/results_service.py` |
| Execution Orchestrator | `app/services/orchestrator/` (`state_machine.py`, `watchdog.py`, `report_validator.py`) |
| Project / Test Case / Results / Execution Repository | `app/repositories/*.py` |
| AI Service Client | `app/integration/ai_client.py` |
| Job Publisher | `app/integration/job_publisher.py` |

This table becomes the M3 "architecture conformance" mapping.

## 5. Contract additions found while writing Phase 1 (to record as ADR-009 in M3 §4 "Design changes")

1. `POST /api/projects/{projectId}/tests` — manual test entry. M2 §3.2 says manual entry stays available when AI is down but M2 §4.2 had no endpoint for it.
2. `GET /api/projects` — list the user's projects (needed by the UI home screen).
3. `409 VERSION_CONFLICT` — approve request must carry the `version` being approved (ADR-005 version-bound approval).
4. `requirementId` on `POST …/tests/generate` and `GET /api/me`.

None of these changes a container, boundary or ASR.
