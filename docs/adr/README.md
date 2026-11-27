# Architecture Decision Records

Template: Appendix A of the course brief (number & title, status, date & deciders, context, alternatives
considered, decision, rationale, consequences).

## Decisions from Milestone 2 (full text: M2 SAD §5)

| ADR | Title | M2 status | Status after M3 |
|---|---|---|---|
| ADR-001 | Combine a Layered Core Backend with Event-Driven Execution | Accepted | Accepted — implemented as designed |
| ADR-002 | REST for requests, AMQP for execution | Proposed | **Accepted** — confirmed by the integrated system (Phase 4); AMQP client in the core refined by ADR-012 |
| ADR-003 | Docker Compose and one sandbox container per run | Proposed | **Accepted** — host = Docker Desktop/WSL 2 (D-04 closed); sandbox details refined by ADR-014 |
| ADR-004 | One PostgreSQL database with single-writer ownership | Accepted | Accepted — enforced by import-linter, compose rules and DB CHECK constraints |
| ADR-005 | Human-in-the-loop, version-bound test approval | Accepted | Accepted — made enforceable over HTTP by ADR-009 |
| ADR-006 | Pass/fail comes only from the test runner | Accepted | Accepted — "valid output" defined by ADR-013 |
| ADR-007 | One language and test framework in the MVP (Python + pytest) | Proposed | **Accepted** — OI-001 closed in Phase 1 |
| ADR-008 | Transparent rule-based risk summary | Accepted | Accepted — implemented (FAILED_TEST, UNTESTED_REQUIREMENT, INTERRUPTED_RUN) |

No M2 decision was superseded. The M3 decisions below **refine** or **add to** them.

## New decisions in Milestone 3 (design changes)

| ADR | Title | Refines | Found in |
|---|---|---|---|
| [ADR-009](ADR-009-contract-refinements.md) | Contract refinements found while fixing the prototype interfaces | M2 §4, §3.6, ADR-005 | Phase 1 |
| [ADR-010](ADR-010-quorum-queues-delivery-limit.md) | Quorum queues with a delivery limit and dead-letter queues | ADR-002 | Phase 2 |
| [ADR-011](ADR-011-membership-check-in-business-layer.md) | Project-membership check moves to the business layer | M2 §3.2 Auth & Access Filter | Phase 2 |
| [ADR-012](ADR-012-sync-amqp-client-in-core.md) | Synchronous AMQP client (pika) in the Core Backend | ADR-002, M2 §3.2 | Phase 4 |
| [ADR-013](ADR-013-strict-runner-report-validation.md) | Strict validation of runner output before PASSED/FAILED | ADR-006 | Phase 2 |
| [ADR-014](ADR-014-sandbox-hardening.md) | Sandbox hardening | ADR-003 | Phase 2 |
| [ADR-015](ADR-015-llm-provider-mock-default-claude-adapter.md) | LLM provider: offline mock by default, Claude adapter, code only on opt-in | OI-003, ASR-5 | Phase 2 |
| [ADR-016](ADR-016-timeout-hierarchy.md) | Timeout hierarchy | ADR-002, QAS-2 | Phases 2/4 |
| [ADR-017](ADR-017-startup-resilience.md) | Start-up resilience: retry, healthcheck, restart policy | ADR-003 | Phase 4 (integration run) |
| [ADR-018](ADR-018-db-session-lifecycle-and-admission-control.md) | DB session lifecycle, pool sizing and admission control | ADR-004, QAS-1 | Phase 5 (QAS-1 load test) |

New ADRs go in this folder as `ADR-0NN-short-title.md`. A decision that replaces an older one marks the older
one "Superseded by ADR-0NN".
