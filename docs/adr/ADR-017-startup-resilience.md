# ADR-017: Start-up resilience: worker connection retry, AMQP-port healthcheck, restart policy

| Field | Content |
|---|---|
| ADR number & title | ADR-017: Start-up resilience: worker connection retry, AMQP-port healthcheck, restart policy |
| Status | Accepted |
| Date & deciders | 27 November 2026 - Member 2 (found in the first docker compose run, Phase 4) |
| Context | In the first integrated run one Runner Worker exited for good: RabbitMQ reported healthy before its AMQP port accepted connections, and aio-pika's robust connection only reconnects after a first success. The worker pool silently halved (ASR-4). |
| Alternatives considered | 1. Ignore it: rare, but silently halves capacity.<br>2. A stronger `depends_on` healthcheck only: fixes start order, not later broker restarts.<br>3. Retry the first connection with capped backoff + healthcheck `check_port_connectivity` + `restart: unless-stopped` for long-running services (chosen). |
| Decision | `runner-worker/worker/main.py::connect_with_retry()`; healthcheck and restart policies in `docker-compose.yml`. |
| Rationale | Defence in depth for an availability problem that only the integrated system revealed. |
| Consequences | + Both workers consume whatever the start order; containers recover from crashes. + 2 regression tests. - Restart policies also bring containers back after a manual stop from Docker Desktop (seen in Phase 5). |
