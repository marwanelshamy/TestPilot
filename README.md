# TestPilot AI

AI-assisted software testing platform: the AI suggests pytest test cases from requirements and explains failures; humans review and approve; only approved tests run inside an isolated sandbox; pass/fail comes only from the real test runner.

CSE4203 Principles of Software Architecture — Milestone 3 architectural prototype.
Team: Marwan El Shamy, Mahmoud Amr, Ahmed Walid, Nada Awad, Lelwar Sadek.

> **Status: Phase 1 (agreement & setup) done.** Contracts, schema and skeleton are in place; services are implemented in Phase 2.

## Architecture summary

Layered Core Backend + event-driven test execution (ADR-001).

| Container | Folder | Tech |
|---|---|---|
| Web UI | `web-ui/` | React + TypeScript, Nginx |
| Core Backend (only writer of execution status) | `core-backend/` | Python 3.12, FastAPI, SQLAlchemy |
| AI Assistance Service (no DB) | `ai-service/` | FastAPI, provider adapters, circuit breaker |
| Message Broker | — | RabbitMQ 3.13 |
| Runner Worker (trusted) | `runner-worker/` | Python, Docker SDK |
| Test Sandbox (untrusted, one per run) | `sandbox-image/` | python:3.12-slim + pytest, no network |
| Database | `db/` | PostgreSQL 16 |

Use cases in the prototype: **UC-1** create project + requirements, **UC-2** AI-generate / review / approve tests, **UC-3** run approved tests and see real results (details: `docs/phase1/01-use-cases.md`).

## Run (after Phase 2)

```bash
cp .env.example .env
docker compose up --build
# UI:        http://localhost:8080
# RabbitMQ:  http://localhost:15672
```

Requires Docker Desktop (Windows/macOS) or Docker Engine + Compose v2 (Linux).

## Demo accounts

| Role | E-mail |
|---|---|
| Developer | dev@testpilot.local |
| QA Assistant | qa@testpilot.local |
| Team Lead | lead@testpilot.local |
| Admin | admin@testpilot.local |

Password: set by the seed script in Phase 2 and documented here.

## Documentation

- `docs/phase1/` — agreed use cases, locked stack, contracts & data, repo/team split
- `docs/contracts/` — REST (OpenAPI) and message (JSON Schema) contracts
- `docs/adr/` — architecture decision records
- `db/schema.sql` — database schema

## Contributing

Branch from `develop` as `feature/<area>-<name>`, open a PR into `develop`. See `docs/phase1/04-repository-and-team-split.md`.
