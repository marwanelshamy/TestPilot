# Core Backend

FastAPI service that owns the database, the approval gate and the **Execution Orchestrator — the only
writer of execution status** (ASR-3, ADR-006). Layered: `api → services → repositories | integration`.

## Run locally (without Docker)

```bash
cd core-backend
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt      # Windows  (Linux/macOS: .venv/bin/pip)
.venv/Scripts/alembic upgrade head                      # creates ./testpilot-dev.db (SQLite) by default
.venv/Scripts/python -m app.seed                        # demo accounts + "Calculator Demo" project
.venv/Scripts/uvicorn --factory app.main:create_app --reload --port 8000
# API docs: http://localhost:8000/docs
```

Set `DATABASE_URL=postgresql+psycopg://user:pass@host:5432/testpilot` to use PostgreSQL. In Docker Compose
the container runs `alembic upgrade head && python -m app.seed && uvicorn ...` automatically.

Demo accounts (password `TestPilot#2026`, from `DEMO_PASSWORD`): `dev@`, `qa@`, `lead@`, `admin@testpilot.local`.

## Tests and architecture checks

```bash
.venv/Scripts/python -m pytest                 # unit + integration (in-memory SQLite)
TEST_DATABASE_URL=postgresql+psycopg://... .venv/Scripts/python -m pytest   # same suite on PostgreSQL
.venv/Scripts/lint-imports                     # layer rules (.importlinter)
.venv/Scripts/ruff check app tests migrations
```

| Suite | What it proves |
|---|---|
| `tests/unit/test_report_validator.py` | ADR-006 / QAS-7: crashed, timed-out, invalid or inconsistent runner output is never PASSED |
| `tests/unit/test_state_machine_and_breaker.py` | P10 terminal states are final; P9 circuit breaker CLOSED → OPEN → HALF_OPEN |
| `tests/unit/test_schema_drift.py` | ORM models == `db/schema.sql` (agreed contract) |
| `tests/integration/test_api_uc1_uc2.py` | UC-1, UC-2 over HTTP; roles; AI outage → 503 while core keeps working (QAS-2) |
| `tests/integration/test_execution_uc3.py` | UC-3: approval-in-transaction, message matches the I4 JSON Schema, lifecycle, duplicates, watchdog |
| `tests/integration/test_reports.py` | coverage, rule-based risks, quality report |

## Component → module map (M3 conformance table)

| C4 L3 component | Module |
|---|---|
| Auth & Access Filter | `app/api/deps/auth.py` (token + role); membership in `app/services/_access.py` |
| Project API / Test Case & Approval API / Execution & Results API | `app/api/routers/{projects,tests,executions}.py` |
| Execution Event Listener | `app/api/listeners/execution_events.py` — **Member 2** |
| Project Service / Test Case & Approval Service / Results & Reporting Service | `app/services/{project,test_case,results}_service.py` |
| Execution Orchestrator | `app/services/orchestrator/` (`__init__`, `state_machine`, `report_validator`, `watchdog`) |
| Project / Test Case / Results / Execution Repository | `app/repositories/*_repository.py` (+ `user_repository.py`) |
| AI Service Client | `app/integration/ai_client.py` |
| Job Publisher | `app/integration/job_publisher.py` (port + log/in-memory adapters; AMQP adapter — **Member 2**) |
| Shared contracts / config / errors | `app/core/` |

## Hand-off points for the other members

* **Member 2 (Runner + RabbitMQ):** implement an AMQP `JobPublisher` (raise `PublishFailed` if the broker
  does not confirm) and select it in `app/main.py::build_publisher` with `JOB_PUBLISHER=amqp`; implement the
  listener described in `app/api/listeners/execution_events.py`. Message models: `app/core/messages.py`.
  Runner must name test files `test_tc_<id>_v<version>.py` (see `test_file_name`).
* **Member 3 (AI service):** implement `docs/contracts/ai-service-api.openapi.yaml`. The client already
  handles timeout, retry, breaker and invalid responses; `tests/conftest.py::FakeAi` shows the exact shapes.
* **Web UI:** all endpoints are live at `/api/*`; OpenAPI at `/docs` matches `docs/contracts/public-api.openapi.yaml`.
