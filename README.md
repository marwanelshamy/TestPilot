# TestPilot AI

**AI-assisted software testing platform — Milestone 3 architectural prototype.**
CSE4203 Principles of Software Architecture · Team: Marwan El Shamy, Mahmoud Amr, Ahmed Walid, Nada Awad, Lelwar Sadek.

The AI suggests pytest test cases from requirements and explains failures; **people review and approve**; only
approved tests run, each in an **isolated Docker sandbox**; **pass/fail comes only from the real test runner**,
never from the AI.

## Overview

| Use case (M1 Must FRs) | What you can do |
|---|---|
| UC-1 Create project & requirements (FR-01, FR-02) | create a Python/pytest project, add requirements |
| UC-2 Generate, review, approve tests (FR-03 – FR-05) | AI suggestions stored as DRAFT, edit (new version → DRAFT), approve/reject **this version**, flag issues |
| UC-3 Run approved tests, see real results (FR-06 – FR-08) | queued run, sandbox execution, per-test PASSED/FAILED + pytest logs, AI explanation labelled as hypothesis |
| UC-4 Quality overview (FR-10 – FR-12) | coverage, rule-based risks, quality report (Team Lead) |

## Architecture summary

Layered Core Backend + event-driven test execution (ADR-001). Seven containers (C4 Level 2):

```
Browser ──HTTPS──► web-ui (Nginx + React) ──/api──► core-backend (FastAPI) ──SQL──► postgres
                                                        │   │
                              REST + circuit breaker    │   │  AMQP (quorum queues + DLQ)
                                                        ▼   ▼
                                               ai-service   rabbitmq ◄──► runner-worker ×2 ──Docker API──► test sandbox (one per run,
                                                   │                                                     no network, non-root, read-only,
                                          LLM adapter: mock | Claude                                     CPU/memory/pids/time limits)
```

| Container | Folder | Technology | Key responsibility / tactics |
|---|---|---|---|
| Web UI | `web-ui/` | React 19, TypeScript, Vite, Nginx | screens for UC-1..UC-4; only talks to `/api` |
| Core Backend | `core-backend/` | Python 3.12, FastAPI, SQLAlchemy, Alembic, pika | API, roles, approval gate, **Execution Orchestrator (only writer of status)**, watchdog, admission control |
| AI Assistance Service | `ai-service/` | FastAPI, provider adapters | redaction pipeline, circuit breaker, rate limit, cache; no database |
| Message broker | (image) | RabbitMQ 3.13 | durable quorum queues, dead-letter queues |
| Runner Worker | `runner-worker/` | Python, aio-pika, Docker SDK | one job at a time, heartbeats, raw results |
| Test Sandbox | `sandbox-image/` | python:3.12-slim + pytest | runs untrusted test code, then is destroyed |
| Database | `db/schema.sql` | PostgreSQL 16 | 13 entities + `processed_message` |

Details: M2 SAD, [`docs/architecture/conformance.md`](docs/architecture/conformance.md) (code mapping),
[`docs/adr/`](docs/adr/) (decisions), [`docs/contracts/`](docs/contracts/) (REST and message contracts).

## Setup and run

**Prerequisites:** Docker Desktop (Windows/macOS, with WSL 2 on Windows) or Docker Engine + Compose v2 (Linux).
Nothing else is needed to run the system.

```bash
git clone https://github.com/marwanelshamy/TestPilot.git
cd TestPilot
cp .env.example .env                 # local-only defaults; LLM_PROVIDER=mock works offline
docker compose up --build            # one command: builds 5 images and starts 7 services
```

Open **http://127.0.0.1:8080** (first start ≈ 2–5 min to build; then ≈ 20 s).
Stop: `docker compose down` (add `-v` to delete the database).

| URL | What |
|---|---|
| http://127.0.0.1:8080 | Web UI (Nginx) |
| http://127.0.0.1:8080/api/health | Core Backend health |
| http://127.0.0.1:15672 | RabbitMQ console (`testpilot` / `RABBITMQ_PASSWORD` from `.env`) |

Optional real LLM: set `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY=...` in `.env` (never commit `.env`).

## Demo accounts

Seeded automatically on start (project **"Calculator Demo"** is shared by all three).

| Role | E-mail | Password |
|---|---|---|
| Developer | `dev@testpilot.local` | `TestPilot#2026` |
| QA Assistant | `qa@testpilot.local` | `TestPilot#2026` |
| Team Lead | `lead@testpilot.local` | `TestPilot#2026` |
| Administrator (reserved, FR-13 future) | `admin@testpilot.local` | `TestPilot#2026` |

These are local demo credentials only (change `DEMO_PASSWORD` in `.env` for any shared deployment).

**Two-minute demo:** sign in as Developer → open *Calculator Demo* → choose the requirement → paste code under
test → **✦ Generate tests with AI** → open a test → **Approve v1** → tick it → **▶ Run selected in sandbox** →
watch QUEUED → RUNNING → result with pytest logs → **✦ Explain with AI** on a failure.

## Tests

| Suite | Tests | Command (from the folder shown) |
|---|---|---|
| Core Backend (unit + API + contract) | 75 | `core-backend`: `python -m pytest` · layer rules: `lint-imports` |
| Runner Worker | 31 | `runner-worker`: `python -m pytest` |
| AI Assistance Service | 29 | `ai-service`: `python -m pytest` |
| Web UI | 14 | `web-ui`: `npm install && npm test` |
| Architecture rules (repo-wide) | 17 | repo root: `python -m pytest tests/architecture` |
| **Integration test across all containers (E2E)** | 7 | repo root, system running: `TESTPILOT_URL=http://127.0.0.1:8080/api python -m pytest tests/e2e -v` |

Each Python service: `python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt` (Linux/macOS:
`.venv/bin/pip`). Repo-level suites use `evidence/requirements.txt`. Full plan: [`docs/testing/test-plan.md`](docs/testing/test-plan.md).

## Quality-attribute evidence

| QAS | Result |
|---|---|
| QAS-3 Security (sandbox isolation) | **MET** — 13/13 attacks blocked or contained |
| QAS-7 Reliability (evidence integrity) | **MET** — 40/40 unapproved rejected, 10/10 worker crashes never PASSED |
| QAS-2 Availability (30 min AI outage) | **MET** — 100 % of core requests succeeded |
| QAS-5 Scalability (100 runs / minute) | **MET** — all finished, p95 queue wait 12.8 s |
| QAS-1 Performance (200 users) | **NOT MET** — p95 1.37 s; found and fixed a deadlock (ADR-018) |

Method, numbers and interpretation: [`evidence/RESULTS.md`](evidence/RESULTS.md). How to re-run: [`evidence/README.md`](evidence/README.md).

## Repository structure

```
TestPilot/
├── docker-compose.yml      one-command run (7 services)
├── .env.example            configuration template (copy to .env)
├── web-ui/  core-backend/  ai-service/  runner-worker/  sandbox-image/   one folder per container
├── db/                     schema.sql (agreed data contract), demo-data notes
├── docs/
│   ├── phase1/             agreed use cases, locked stack, contracts & data, team split
│   ├── contracts/          OpenAPI (REST) + JSON Schemas (AMQP messages)
│   ├── architecture/       conformance: component → code mapping, erosion guards, design changes
│   ├── adr/                ADR index + ADR-009..ADR-018 (Milestone 3 design changes)
│   ├── testing/            test plan and evidence matrix
│   └── milestone3/         Milestone 3 document
├── evidence/               quality-attribute experiments, results, RESULTS.md
└── tests/                  repo-level suites: architecture rules, E2E integration test
```

## Branches

`main` (submission) ← `develop` ← `integration/phase4`, `phase5/evidence` ← `feature/*` (one per member area).
