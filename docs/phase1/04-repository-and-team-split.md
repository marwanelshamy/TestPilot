# Phase 1 — Repository, Folder Ownership and Branches

**Repository:** https://github.com/marwanelshamy/TestPilot

## 1. Folder structure

```
TestPilot/
├── docker-compose.yml          one command: docker compose up --build
├── .env.example                copy to .env (never commit .env)
├── db/                         schema.sql (agreed contract), seed-demo.sql
├── docs/
│   ├── phase1/                 use cases, locked stack, contracts summary, this file
│   ├── contracts/              OpenAPI (I1, I2) + JSON Schemas for AMQP messages (I4)
│   ├── adr/                    ADR-001..008 (from M2) + new ones (ADR-009+)
│   └── diagrams/               PlantUML / Mermaid sources (C-14)
├── web-ui/                     React + TS + Vite, served by Nginx          (Web UI container)
├── core-backend/               FastAPI, layered, .importlinter             (Core Backend container)
│   └── app/{api, services/orchestrator, repositories, integration}
├── ai-service/                 FastAPI, redaction, provider adapters       (AI Assistance Service)
├── runner-worker/              AMQP consumer + Docker SDK                  (Runner Worker)
├── sandbox-image/              python:3.12-slim + pytest, non-root         (Test Sandbox image)
├── evidence/                   QAS evidence: k6/Locust scripts, fault-injection results (Phase 3)
└── scripts/                    seed, demo, test helpers
```

## 2. Ownership (proposed — confirm in the team meeting)

Each member owns one area **and** commits in it, so the commit history shows everyone's work (M3 §6). Owners review PRs that touch their area.

| Member | Area / folders | Main deliverables in Phase 2 | M3 report part |
|---|---|---|---|
| **Marwan El Shamy** | `core-backend/app/services/orchestrator/`, `integration/job_publisher.py`, `api/listeners/`, `execution_repository.py` | UC-3 back end: approval-in-transaction, state machine, watchdog, report validation | Design changes (ADR-009+) |
| **Mahmoud Amr** | `core-backend/app/api/`, project/test-case/results services and repositories, auth, migrations, `evidence/` | UC-1 + UC-2 back end, JWT + roles, seed script; load and fault-injection evidence in Phase 3 | Quality attribute evidence |
| **Nada Awad** | `web-ui/` | All screens for UC-1..UC-3 (login, projects, requirements, test review/approve, run + results/logs), AI-unavailable messages | Conformance mapping table |
| **Ahmed Walid** | `ai-service/`, `docs/contracts/` | Mock + one real provider adapter, redaction pipeline, breaker, output validation; keeps contracts in sync | Testing (unit + integration instructions) |
| **Lelwar Sadek** | `runner-worker/`, `sandbox-image/`, `docker-compose.yml`, `db/` | Worker, sandbox limits, compose wiring, health checks, one-command run | README + deployment |

Shared, everyone: `docs/`, cross-boundary integration test(s), the final demo.

## 3. Branching model

| Branch | Purpose | Rules |
|---|---|---|
| `main` | What we submit. Always runs with `docker compose up --build`. | Protected: PR only, 1 approval, no direct push. Merged from `develop` at each milestone checkpoint and tagged (`m3-submission`). |
| `develop` | Integration branch | PR only, 1 approval from the owner of the touched area, CI green |
| `feature/<area>-<short-name>` | One task each | Branched from `develop`, small, merged by PR |
| `fix/<short-name>` | Bug fixes | Same as feature |
| `docs/<short-name>` | Report / ADR work | Same as feature |

Starter feature branches created in Phase 1:

| Branch | Owner |
|---|---|
| `feature/core-execution` | Marwan |
| `feature/core-api` | Mahmoud |
| `feature/web-ui` | Nada |
| `feature/ai-service` | Ahmed |
| `feature/runner-worker` | Lelwar |

## 4. Commit and PR conventions

- Commit messages: `<area>: <imperative summary>` — e.g. `core: add createExecutionIfApproved`, `web-ui: approve button sends version`.
- Each member commits with their **own** Git identity (`git config user.name/user.email`), not one shared account.
- PR description: what changed, which FR/QAS/ADR it implements, how it was tested. Template: `.github/pull_request_template.md`.
- A PR that changes a contract (`docs/contracts/*`, `db/schema.sql`) needs approval from the provider **and** the consumer owner.

## 5. To do on GitHub (repo owner — Marwan)

1. Add the other four members as collaborators.
2. Settings → Branches → protect `main` and `develop` (require PR + 1 review).
3. Set `develop` as the default branch for PRs.
