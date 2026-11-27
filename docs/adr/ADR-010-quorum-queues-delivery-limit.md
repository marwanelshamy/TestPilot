# ADR-010: Quorum queues with a delivery limit and dead-letter queues

| Field | Content |
|---|---|
| ADR number & title | ADR-010: Quorum queues with a delivery limit and dead-letter queues |
| Status | Accepted |
| Date & deciders | 27 November 2026 - Member 2 (Runner Worker + RabbitMQ) |
| Context | M2 specified durable queues with acknowledgements (ADR-002). A job that crashes every worker that takes it (poison message) would be redelivered for ever, blocking capacity and never reaching a terminal state (QAS-5: every job must end; QAS-7). |
| Alternatives considered | 1. Classic durable queues + an application-level retry counter in a header: works, but every consumer must implement and agree on the counting.<br>2. Quorum queues with `x-delivery-limit=3` and a dead-letter queue per queue (chosen): the broker counts redeliveries and dead-letters automatically.<br>3. Discard a message after its first failure: simple, but a worker crash (QAS-7 Part B) would lose valid jobs. |
| Decision | Declare `execution.requests` and `execution.events` as quorum queues with `x-delivery-limit=3`, dead-lettering to `execution.requests.dlq` / `execution.events.dlq` through the default exchange. Invalid messages are rejected without requeue (straight to the DLQ). Both clients declare the identical topology. |
| Rationale | Uses a broker feature instead of hand-written retry logic, in exactly the area where ASR-3 needs guarantees (the reason RabbitMQ was chosen in M2 §3.1.3). |
| Consequences | + Poison jobs and malformed messages end in a DLQ for inspection; normal crashes are still redelivered (QAS-7: 10/10 crashes handled). - Queue arguments must match on every client (RabbitMQ rejects a mismatch), guarded by `test_topology_identical_to_runner_worker`. - Quorum queues use more broker memory than classic queues. |
