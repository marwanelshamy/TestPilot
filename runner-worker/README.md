# Runner Worker

Trusted background worker (C4 container "Runner Worker"). It consumes `ExecutionRequested` jobs from
RabbitMQ, runs each job in a **fresh, locked-down Test Sandbox container**, streams heartbeats, and
publishes the **raw** runner output as `ExecutionFinished`. It never decides pass/fail (the Core
Backend's Execution Orchestrator does, ADR-006) and it has **no database access** (ASR-1, ASR-3).

```
execution.requests ──> [handle_delivery] ──> JobProcessor ──> DockerSandbox ──> Test Sandbox (per run)
                             │  ack / reject / nack          │ heartbeat every 5 s
                             └──────────── execution.events <┘ ExecutionHeartbeat, ExecutionFinished
```

## Modules

| Module | Responsibility | Tactics / patterns |
|---|---|---|
| `worker/main.py` | AMQP consumer, prefetch 1, publisher confirms; ack only after `ExecutionFinished` is confirmed; invalid job → reject → DLQ; failure → nack/requeue | P4, T16, T17, T10 |
| `worker/processor.py` | Heartbeat loop while the sandbox runs; builds `ExecutionFinished`; caps stdout/stderr; drops oversized reports | T1, T2 |
| `worker/sandbox.py` | Docker driver: create → copy tests → start → wait(limit) → kill on timeout → collect logs + JUnit XML → always remove container + volume | P6, T5, T7, T8, T11, T13 |
| `worker/topology.py` | Quorum queues, `x-delivery-limit=3`, dead-letter queues | ASR-4, QAS-5 |
| `worker/messages.py` | Contract I4 models; `test_file_name()` naming agreed with the Core Backend | T10 |
| `worker/config.py` | Environment settings (no DB, no LLM key) | T24 |

Sandbox restrictions: see `../sandbox-image/README.md`.

## Run

In Docker Compose (normal way): `docker compose up --build` starts 2 worker replicas
(`docker compose up --scale runner-worker=4` for more).

Locally (needs Docker and a RabbitMQ):

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt
docker build -t testpilot-sandbox:latest ../sandbox-image
AMQP_URL=amqp://guest:guest@localhost:5672/ .venv/Scripts/python -m worker.main
```

| Variable | Default |
|---|---|
| `AMQP_URL` | `amqp://guest:guest@localhost:5672/` |
| `SANDBOX_IMAGE` | `testpilot-sandbox:latest` |
| `HEARTBEAT_INTERVAL_SECONDS` | `5` |
| `WORKER_ID` | container hostname |
| `SANDBOX_PIDS_LIMIT` / `SANDBOX_TMPFS_MB` | `128` / `64` |

## Tests

```bash
.venv/Scripts/python -m pytest        # 29 tests, no Docker or RabbitMQ needed
.venv/Scripts/ruff check worker tests
```

| Test file | What it proves |
|---|---|
| `tests/test_contract.py` | Jobs accepted and events emitted match the shared JSON Schemas (I4), formats included |
| `tests/test_sandbox.py` | Isolation options (no network, read-only, non-root, no caps, CPU/mem/pids limits); timeout → kill → TIMEOUT; OOM → RESOURCE_LIMIT; Docker failure → ERROR; container always removed |
| `tests/test_processor_and_delivery.py` | Heartbeats during the run, ExecutionFinished last; ack/reject/requeue rules; size caps |
| `tests/test_real_pytest_output.py` | Real pytest with the sandbox's exact command produces the report shape the Core Backend validates |

## Known limits (to record for M4 ATAM)

* Not yet exercised against a real Docker daemon / RabbitMQ on this machine (Docker not installed). Phase 4
  must run the end-to-end flow and the QAS-3 security suite in Docker.
* The worker needs the Docker socket (risk R-009). It never runs user code; a socket proxy that only allows
  container create/start/kill/remove would reduce the risk further.
* A test file that cannot be imported makes pytest exit with code 2; the orchestrator then records
  INTERRUPTED / INVALID_REPORT (never PASSED). Showing it as an ERROR for that test is a possible UX improvement.
