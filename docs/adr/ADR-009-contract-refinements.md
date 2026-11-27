# ADR-009: Contract refinements found while fixing the prototype interfaces

| Field | Content |
|---|---|
| ADR number & title | ADR-009: Contract refinements found while fixing the prototype interfaces |
| Status | Accepted |
| Date & deciders | 27 November 2026 - Phase 1 contract session, whole team (Member 1 and Member 4 lead) |
| Context | Writing the OpenAPI, JSON-Schema and SQL contracts in Phase 1 exposed gaps in M2 §4 and §3.6: M2 §3.2 requires manual test entry while the AI is down but §4.2 had no endpoint; ADR-005 binds approval to a version but the approve request did not carry one; the broker can be down when a run is requested; termination reasons existed only in prose; duplicate AMQP events had no place to be recorded (R-011). Related: ASR-2, ASR-3, QAS-2, QAS-7, C-04. |
| Alternatives considered | 1. Keep the M2 interfaces and solve the gaps inside the code (hidden behaviour): no contract change, but the UI and runner owners cannot rely on the behaviour and nothing is testable against a contract.<br>2. Extend the contracts additively and record the change (chosen): every member works against the same written contract; contract tests catch drift; costs one review round. |
| Decision | Add to contract I1: `POST /projects/{id}/tests` (manual entry), `GET /projects`, `GET /me`, `GET /projects/{id}/executions`; `ApprovalDecision.version` with `409 VERSION_CONFLICT`; `503 QUEUE_UNAVAILABLE` (execution insert rolled back). Add enums `INVALID_REPORT`, `RESOURCE_LIMIT`, `INTERNAL_ERROR` and worker outcome `RESOURCE_LIMIT`. Data: table `processed_message`, columns `execution.time_limit_seconds` and `execution_evidence.truncated`, and CHECK constraints that forbid PASSED/FAILED without `termination_reason = COMPLETED`. |
| Rationale | All additions are backward compatible, keep every container and boundary of M2, and make ASR-3 enforceable at three levels (API, orchestrator, database). |
| Consequences | + Manual entry keeps the core workflow usable during an AI outage (QAS-2: 100 % success). + Version-bound approval and the DB CHECK constraints are verified by tests and by QAS-7. - One more table and six more endpoints to maintain. Follow-up: keep `docs/contracts/` and code in sync (contract tests in each service). |
