# Architecture Decision Records

Template: Appendix A of the course brief (number & title, status, date & deciders, context, alternatives, decision, rationale, consequences).

| ADR | Title | Status | Source |
|---|---|---|---|
| ADR-001 | Combine a Layered Core Backend with Event-Driven Execution | Accepted | M2 SAD §5 |
| ADR-002 | REST for requests, AMQP for execution | Accepted | M2 SAD §5 |
| ADR-003 | Docker Compose and one sandbox container per run | Accepted | M2 SAD §5 |
| ADR-004 | One PostgreSQL database with single-writer ownership | Accepted | M2 SAD §5 |
| ADR-005 | Human-in-the-loop, version-bound test approval | Accepted | M2 SAD §5 |
| ADR-006 | Pass/fail comes only from the test runner | Accepted | M2 SAD §5 |
| ADR-007 | One language and framework in the MVP (Python + pytest) | Accepted (confirmed Phase 1) | M2 SAD §5 |
| ADR-008 | Transparent rule-based risk summary | Accepted | M2 SAD §5 |
| ADR-009 | Contract refinements for the prototype | Proposed | `docs/phase1/03-contracts-and-data.md` §5 — write up in M3 |

New ADRs go in this folder as `ADR-0NN-short-title.md`. A decision that replaces an old one marks the old one "Superseded by ADR-0NN".
