# Phase 1 — Agreed End-to-End Use Cases (Milestone 3)

**Status:** Agreed baseline for M3 · **Source:** M1 FR table, M2 SAD §1.2, §3.3, §4.2
**Rule (M3 brief):** at least 3 end-to-end use cases from the M1 *Must* list. We commit to **three** and keep one stretch use case.

| UC | Name | FRs covered (all *Must*) | Main roles | Crosses which boundaries |
|----|------|--------------------------|------------|--------------------------|
| UC-1 | Create a project and enter requirements | FR-01, FR-02 | Developer | Web UI → Core Backend → PostgreSQL |
| UC-2 | Generate, review and approve AI test cases | FR-03, FR-04, FR-05 | Developer, QA Assistant, Team Lead | Web UI → Core Backend → AI Assistance Service → LLM adapter |
| UC-3 | Run approved tests and see the real runner result | FR-06, FR-07 (+ FR-08 basic logs) | Developer, QA Assistant, Team Lead | Web UI → Core Backend → RabbitMQ → Runner Worker → Test Sandbox → back |
| UC-4 *(stretch)* | Generate a basic quality report | FR-12 (+ FR-10/FR-11 basic) | Team Lead | Web UI → Core Backend → PostgreSQL |

Together UC-1 → UC-3 are the M1 "minimum demonstrable path": create project → enter requirements → generate tests → review/approve → execute → real results and logs.

---

## UC-1 — Create a project and enter requirements

| Field | Content |
|---|---|
| Primary actor | Developer (Team Lead may also create projects, per M2 §4.2) |
| Preconditions | User is logged in (JWT, assumption A-04) |
| Trigger | User clicks **New project** |
| Main flow | 1. User enters a project name. Language/framework are fixed to **Python + pytest** (C-01, ADR-007). 2. `POST /api/projects` → Core Backend stores PROJECT and adds the creator as PROJECT_MEMBER → `201 {projectId}`. 3. User adds one or more requirements (`POST /api/projects/{id}/requirements`) → `201 {requirementId}`. 4. UI lists requirements (`GET …/requirements`, paginated). |
| Alternative / error flows | Missing name or requirement text → `400 VALIDATION_ERROR`. No/expired token → `401 AUTH_REQUIRED`. Role not allowed → `403 FORBIDDEN`. |
| Postconditions | Project and requirements stored in PostgreSQL. |
| Acceptance criteria | AC-1.1 a new project appears in the list with stack "Python / pytest". AC-1.2 requirements are listed in creation order. AC-1.3 a QA Assistant cannot create a project (403). |
| Architecture shown | Layers P1 (API → Service → Repository), JWT auth T9, Repository P7. |

## UC-2 — Generate, review and approve AI test cases

| Field | Content |
|---|---|
| Primary actors | Developer or QA Assistant (generate, edit); Developer or Team Lead (approve/reject) |
| Preconditions | UC-1 done: project with at least one requirement |
| Main flow | 1. User selects a requirement and clicks **Generate tests** → `POST /api/projects/{id}/tests/generate`. 2. Core Backend's AI Service Client calls the AI Assistance Service `POST /v1/test-suggestions` (timeout + retry + circuit breaker). 3. AI Service redacts secrets, minimizes context, calls the LLM through the provider adapter, schema-validates the output. 4. Suggestions are stored as TEST_CASE rows with `status = DRAFT`, `source = AI_GENERATED`, `version = 1`, linked to the requirement → `201 {testIds}`. 5. User edits a test (`PUT /api/tests/{id}`) → version + 1, status back to DRAFT. 6. Developer/Team Lead approves (`POST /api/tests/{id}/approve` with `version`) → TEST_APPROVAL row, status APPROVED. Or rejects. |
| Alternative flows | **AI unavailable** (provider down, timeout, breaker open) → `503 AI_UNAVAILABLE`; UI shows a clear message, the user can still add a test manually (`POST /api/projects/{id}/tests`, source MANUAL). Invalid model output → rejected, never stored. Approving a stale version → `409 VERSION_CONFLICT`. QA Assistant tries to approve → `403 FORBIDDEN`. |
| Postconditions | Test cases exist with approval state bound to a version (ADR-005). |
| Acceptance criteria | AC-2.1 AI output is labelled "AI-generated" in the UI (C-10). AC-2.2 editing an approved test resets it to DRAFT. AC-2.3 with the AI service stopped, the project, requirements and stored tests still load (QAS-2). |
| Architecture shown | Separate AI container (ASR-2), circuit breaker P9/T1/T3/T4, provider adapter P8 (ASR-5), redaction pipe-and-filter P5, approval gate T9. |

## UC-3 — Run approved tests and see the real runner result

| Field | Content |
|---|---|
| Primary actors | Developer, QA Assistant or Team Lead |
| Preconditions | UC-2 done: at least one APPROVED test |
| Main flow | 1. User selects approved tests and clicks **Run** → `POST /api/executions`. 2. Execution Orchestrator checks approval **and** inserts the EXECUTION row (status QUEUED) in one DB transaction. 3. Job Publisher sends `ExecutionRequested` to RabbitMQ → API replies `202 {executionId, status: QUEUED}` immediately. 4. A Runner Worker takes the job, sends `ExecutionHeartbeat` (status → RUNNING), starts a fresh Test Sandbox (no network, non-root, CPU/memory/time limits), collects exit code + JUnit-XML + logs, removes the sandbox. 5. Worker publishes `ExecutionFinished`. 6. Orchestrator validates the report; writes PASSED/FAILED (valid report) or INTERRUPTED (invalid/missing/timeout) together with evidence in one transaction, then the message is acked. 7. UI polls `GET /api/executions/{id}` until terminal and shows per-test results and logs (`GET …/logs`). |
| Alternative flows | Any selected test not approved → `409 TEST_NOT_APPROVED`, no execution created. Time limit exceeded → INTERRUPTED (TIMEOUT). Worker crash / heartbeats stop → watchdog sets INTERRUPTED (RUNNER_LOST). Duplicate or late `ExecutionFinished` for a terminal run → ignored. |
| Postconditions | Every execution reaches exactly one terminal state, traceable to an execution ID and runner evidence. |
| Acceptance criteria | AC-3.1 a failing pytest test shows FAILED with its assertion message. AC-3.2 an unapproved test can never run. AC-3.3 a killed worker or invalid report never produces PASSED (QAS-7). AC-3.4 an infinite-loop test is stopped after its time limit (QAS-3). |
| Architecture shown | Event-driven execution P4 (ASR-4), state machine P10 + single writer (ASR-3), sandbox isolation P6/T7/T8 (ASR-1), heartbeat watchdog T1, transactions T6. |

## UC-4 (stretch) — Basic quality report

Team Lead calls `POST /api/projects/{id}/reports` → Core Backend aggregates latest results, requirement coverage (requirements with no linked test) and a rule-based risk list (failed tests, untested requirements) into QUALITY_REPORT (JSONB). Only done if UC-1…UC-3 are finished and tested.

---

## Which M3 tactics these use cases demonstrate (≥2 required)

| Tactic | Shown in | QAS to measure in Phase 3 |
|---|---|---|
| Retry + timeout + circuit breaker, degradation (T1, T3, T4, P9) | UC-2 | QAS-2 fault-injection |
| Message queue with competing consumers (P4, T16, T17) | UC-3 | QAS-5 load test |
| Authenticate/authorize actors, approval gate (T9) | UC-1, UC-2, UC-3 | QAS-7 approval-negative tests |
| Sandbox isolation + bounded execution time (T7, T8, T13) | UC-3 | QAS-3 security suite |
| Heartbeat watchdog + sanity checking (T1, T2) | UC-3 | QAS-7 fault-injection |
