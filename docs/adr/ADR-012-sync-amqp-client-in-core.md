# ADR-012: Synchronous AMQP client (pika) in the Core Backend; event listener in a background thread

| Field | Content |
|---|---|
| ADR number & title | ADR-012: Synchronous AMQP client (pika) in the Core Backend; event listener in a background thread |
| Status | Accepted |
| Date & deciders | 27 November 2026 - Member 2 (Phase 4 integration) |
| Context | M2 §3.2 named aio-pika for the Core Backend's Job Publisher and Event Listener. The Core Backend's endpoints, services and SQLAlchemy sessions are synchronous; an asyncio AMQP client would need a second event loop or an async rewrite of the orchestrator. |
| Alternatives considered | 1. aio-pika in the core: matches M2, but needs async DB access or bridging between event loops.<br>2. pika `BlockingConnection` with publisher confirms; listener as a daemon thread with its own connection (chosen).<br>3. Celery or another task framework: hides AMQP details but adds a large dependency with its own acknowledgement semantics. |
| Decision | Job Publisher: one shared pika connection behind a lock, `confirm_delivery()`, persistent messages, one reconnect, `PublishFailed` leads to 503 and rollback. Listener: background thread, prefetch 20, ack after the orchestrator commits, reject invalid messages to the DLQ, nack/requeue on error, reconnect loop. The Runner Worker keeps aio-pika. |
| Rationale | Fits the synchronous core without changing the message contract or the architecture; only the technology label of two components changes. |
| Consequences | + Verified in Phase 4: RabbitMQ restarted under a running backend, both reconnected. - Two AMQP libraries in the project (pika in the core, aio-pika in the worker); the shared topology is tested for equality. |
