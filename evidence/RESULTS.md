# Quality-Attribute Evidence — Results (M3 §2)

**Phase 5, led by Member 5.** Every measure below was taken on the integrated system started with
`docker compose up --build`, through the public API at `http://127.0.0.1:8080/api` (via Nginx). Targets are the
proposed response measures of M1/M2; per C-16 they are reported as **measured**, met or not met.

**Environment (all runs):** Intel i7-11850H (16 logical CPUs), Windows 11 Pro, Docker Desktop 29.9.3 on WSL 2
(VM memory ≈ 3.7 GB), **2 Runner Worker replicas**, `LLM_PROVIDER=mock`, PostgreSQL 16, RabbitMQ 3.13.
Sandbox limits: 30 s, 1 CPU, 256 MB, pids 128. Watchdog: heartbeat 5 s × 3 missed.
Raw result files with full environment and per-request data: `evidence/<qas>/results/*.json`.

## Summary

| QAS | Attribute (ASR) | Target | Measured | Verdict |
|---|---|---|---|---|
| QAS-3 | Security (ASR-1) | all attacks blocked/contained; 30 s loop killed ≤ 35 s | 13/13 attacks blocked or contained; control passed; loop killed at 32.9 s | **MET** |
| QAS-7 | Reliability (ASR-3) | 100 % unapproved rejected; 100 % crashed/invalid runs never PASSED; traceable | 40/40 rejected, 0 created; 10/10 crashes → INTERRUPTED; fake pass → INTERRUPTED | **MET** |
| QAS-2 | Availability (ASR-2) | ≥ 99 % core requests OK during 30 min AI outage; AI error ≤ timeout + 3 s | 13,493/13,493 core requests OK (100 %); 180/180 AI requests → 503 in ≤ 0.08 s; AI recovered | **MET** |
| QAS-5 | Scalability (ASR-4) | 100 % unique IDs + terminal; ≥ 95 % start ≤ 30 s | 100/100 unique + terminal; 100 % started ≤ 30 s (p95 12.8 s) with 2 workers | **MET** |
| QAS-1 | Performance (not an ASR) | p95 ≤ 500 ms, p99 ≤ 1 s at 200 users | run 3: p95 1.37 s, p99 2.07 s, 0.18 % errors, 77 req/s; found and fixed a connection-pool deadlock (runs 1–2) | **NOT MET** |
| QAS-4 | Modifiability (ASR-5) | ≤ 8 h, ≤ 2 modules | protocol ready (`qas4_modifiability/exercise.md`) — team exercise | not run |
| QAS-6 | Usability | ≥ 9/10 unaided within 5 min | protocol ready (`qas6_usability/protocol.md`) — needs 10 participants | not run |

---

## QAS-3 · Security — isolation of untrusted test code (ASR-1) — **MET**

**Result file:** `qas3_security/results/20261127T025614Z.json` (commit `d7754c9`).

**Method.** 15 test files submitted through the normal workflow (create → approve → run), one run each, in a
real per-run Docker sandbox. Each attack is written so that the test **passes only if the attack succeeds** —
a PASSED attack would be a breach. A benign control test must PASS (proves code really executes) and a helper
plants a marker file for the cross-run check, which runs in a **different project**.

**Results.**

| Case | Attempt | Status | Evidence |
|---|---|---|---|
| control_benign | normal test | PASSED | sandbox executes code |
| read_shadow | read protected file | FAILED | `PermissionError` — runs as uid 10001 |
| docker_socket | reach the Docker daemon | FAILED | socket not present in the sandbox |
| network_internet | open an internet connection | FAILED | `Network is unreachable` |
| network_database | reach PostgreSQL | FAILED | name resolution fails (no network) |
| network_broker | reach RabbitMQ | FAILED | name resolution fails |
| run_as_root | run as root | FAILED | `geteuid() == 10001` |
| secrets_in_env | read service secrets | FAILED | none of 7 secret variables present |
| write_system_dir | write outside /work | FAILED | `Read-only file system` |
| fork_bomb | start 500 processes | INTERRUPTED (RESOURCE_LIMIT) | killed by limits, 4.7 s |
| memory_bomb | allocate 2 GB | INTERRUPTED (RESOURCE_LIMIT) | OOM-killed at 256 MB, 1.9 s |
| fake_pass_exit | `os._exit(0)` before report | INTERRUPTED (INVALID_REPORT) | no valid report → never PASSED |
| plant_marker → cross_run_leak | read data from a previous run / other project | FAILED | nothing survives a run |
| infinite_loop | run forever | INTERRUPTED (TIMEOUT) | killed at **32.9 s** (target ≤ 35 s) |

**Interpretation.** Every attack ended blocked (FAILED inside the sandbox) or contained (INTERRUPTED by
limits), and none could reach the host, the network, the database, the broker or another run. This is the
direct effect of the container-level tactics: separate entities (T7 — one throw-away container per run),
limit exposure (T8 — `network_mode=none`, non-root, read-only root FS, `cap_drop ALL`, no Docker socket),
detect service denial (T11 — memory/pids limits) and bounded execution time (T13 — killed by the Runner Worker
from outside). The fake-pass case shows ASR-1 and ASR-3 working together: the sandbox cannot forge a pass
because the orchestrator requires a complete JUnit report consistent with the exit code.
**Limits:** a documented suite of 13 attacks on one machine; it does not prove that all possible attacks are
prevented (as QAS-3 itself states). Kernel-level container escapes are out of scope.

---

## QAS-7 · Reliability — execution and evidence integrity (ASR-3) — **MET**

**Result file:** `qas7_reliability/results/20261127T105452Z.json` (commit `05daee4`).

**Method.** (A) 40 run requests for tests that are DRAFT, REJECTED, edited after approval, or an approved test
mixed with a draft. (B) 10 times: start a test that sleeps 20 s, wait until RUNNING, `docker kill` **both**
Runner Workers (no healthy worker can finish the job), wait for the final status, then restart the workers so
the redelivered job's late result arrives too. (C) a test that exits the interpreter before pytest writes its
report.

**Results.**

| Part | Target | Measured |
|---|---|---|
| A — approval gate | 100 % rejected, 0 executions created | **40/40** answered `409 TEST_NOT_APPROVED`; **0** executions created |
| B — runner crash | 100 % non-passing terminal state, traceable | **10/10** `INTERRUPTED / RUNNER_LOST`, each with execution ID + runner log evidence; detection after **13.5 s (min) · 16.8 s (median) · 19.8 s (max)**; late results of the redelivered jobs ignored |
| C — invalid output | never PASSED | `INTERRUPTED / INVALID_REPORT` |

**Interpretation.** (A) holds because the approval check and the execution insert happen in **one database
transaction** inside the Execution Orchestrator (T9, ADR-005); an edited test loses its approval because
approval is bound to the version. (B) holds because only the orchestrator writes status (ADR-006, single
writer), the heartbeat watchdog turns silence into `INTERRUPTED` (T1), and the `processed_message` table plus
"terminal states never change" make the redelivered job's later result harmless (R-011). (C) holds because
PASSED/FAILED require a valid, complete report (T2) — also enforced by a DB CHECK constraint.
**Detection time** (13.5–19.8 s) equals the watchdog window (3 missed heartbeats × 5 s) plus up to one sweep
interval (5 s). The current QAS-7 has no detection-time target; M1's earlier testability scenario proposed
≤ 10 s, which this configuration would **not** meet. It is a tunable sensitivity point (OI-007): a 2 s heartbeat
would give ≈ 6–8 s at the cost of more broker traffic — record as a trade-off for the M4 ATAM.

---

## QAS-2 · Availability — graceful handling of an AI-provider outage (ASR-2) — **MET**

**Result file:** `qas2_ai_outage/results/20261127T112539Z.json`.

**Method.** Baseline check that AI generation works (201). Then `docker compose stop ai-service` for **30 minutes**
(the M1 duration). During the outage, one client cycled continuously through the unaffected core functions
(read project, requirements, tests, executions, an execution, its logs, coverage, risks; and *add a manual test*),
while a second client asked for AI test generation every 10 s and timed the answer. Afterwards the AI service
was started again and generation retried until it succeeded.

**Results.**

| Measure | Target | Measured |
|---|---|---|
| Core requests succeeding during the outage | ≥ 99 % | **13,493 / 13,493 = 100 %** |
| AI requests answered with an actionable error | all | **180 / 180** `503 AI_UNAVAILABLE` |
| Time until the user gets the AI error | ≤ configured timeout (60 s) + 3 s | **max 0.08 s**, p95 0.06 s |
| AI after recovery | works again | `201` — suggestions generated |

**Interpretation.** The AI Assistance Service is its own container behind a synchronous REST link that the
Core Backend wraps in a timeout, a circuit breaker and degradation (P9, T1, T4 — ADR-002). Its outage therefore
removes only the AI features: everything stored in PostgreSQL stays usable, and manual test entry keeps the core
workflow going. The breaker opened after 5 failures (`details.reason = CIRCUIT_OPEN`), after which AI requests
were answered without any network attempt; it closed again on its own after the reset period.
**Limit:** stopping the container makes its host name unresolvable, so every call failed **fast**. This proves the
*provider down* case; a provider that **hangs** until the 60 s timeout was not injected (it needs a delay proxy, e.g.
toxiproxy). By design that case is bounded by `AI_CLIENT_TIMEOUT_SECONDS` and then served from the open breaker.

---

## QAS-5 · Scalability — concurrent test executions (ASR-4) — **MET**

**Result file:** `qas5_concurrency/results/20261127T112714Z.json`.

**Method.** One project with one quick approved test. 100 `POST /api/executions` spread evenly over 60 s by 10
parallel clients; then every execution polled until terminal. Queue wait = `startedAt − createdAt` (time from
acceptance until a Runner Worker's first heartbeat). **Tested worker capacity: 2 Runner Worker replicas.**

**Results.**

| Measure | Target | Measured |
|---|---|---|
| Requests accepted with a unique execution ID | 100 % | **100 / 100**, all unique (sent in 59.9 s) |
| Executions reaching a terminal state | 100 % | **100 / 100** (all PASSED) |
| Jobs starting within 30 s | ≥ 95 % | **100 %** — queue wait p50 **7.5 s**, p95 **12.8 s**, max **13.2 s** |

**Interpretation.** Requests are accepted immediately (`202`) and queued in RabbitMQ (P4); two competing Runner
Workers each take one job at a time (prefetch 1, T16/T17), each in a fresh sandbox. The queue absorbed the burst
and the wait stayed under half the target. The wait grows with arrival rate ÷ worker capacity: each sandbox run
costs ≈ 1 s of container start-up, so 2 workers sustain roughly 1.7 runs/s; at 100 runs/min the system ran close to
that capacity, which is why waits rose to ~13 s. **Sensitivity point:** more replicas
(`docker compose up -d --scale runner-worker=N`) or pre-warmed sandboxes lower the wait — the isolation-vs-speed
trade-off of M1 §7.5 (ASR-1 vs ASR-4).

---

## QAS-1 · Performance — fast test-result retrieval (not an ASR) — **NOT MET** (2 defects found and fixed)

**Result files:** `qas1_retrieval/results/*-run1-before-fix.json`, `*-run2-session-fix-only.json`,
`*-run3-admission-control.json`, and `run2-pyspy-thread-dump.txt` (live thread dump of the hung backend).

**Method.** One project seeded inside the Core Backend container with **1,000 test cases and 10,000 finished
executions** (`seed_results.py`, verified in PostgreSQL). **200 concurrent users for 15 minutes**, each looping:
latest results page (`GET /projects/{id}/executions`, first page of 20) then one execution (`GET /executions/{id}`),
0.5 s think time, 10 s client timeout. Latency measured end to end through Nginx. Load generator on the same laptop.
Unloaded reference: a single results request takes **14–16 ms** (page 1 or page 500), so the indexes and
pagination (T15) work.

**Results.**

| Run | Change | Requests | Errors | p50 | p95 | p99 | Throughput | Backend after the load |
|---|---|---|---|---|---|---|---|---|
| 1 | M3 code as integrated | 11,774 | **96.6 %** | 0.51 s* | 1.44 s* | 1.54 s* | 13/s | **hung**: 15 connections "idle in transaction", health dead |
| 2 | session released on the event loop | — | — | — | 2.19 s | 2.35 s | — | **hung**: 30 connections stuck, health dead |
| 3 | + admission control (25 in flight) | **69,264** | **0.18 %** | 0.96 s | **1.37 s** | **2.07 s** | **77/s** | **healthy**, no stuck connections |

\* run 1 latencies cover only the 3 % of requests that succeeded.

**What the experiment found.** Under 200 users the backend **deadlocked** (run 1). A live `py-spy` dump (run 2)
showed all 40 API worker threads blocked waiting for a database connection, while every connection was held by
a request that had *finished* and was waiting for a worker thread to serialise its response — a convoy deadlock
between FastAPI's thread pool and SQLAlchemy's connection pool. Cancelled requests also leaked connections
because the session clean-up ran on the same exhausted thread pool. Two fixes (design changes #14, #15):
1. the DB-session dependency became an async generator, so its clean-up runs on the event loop and always
   returns the connection — even when the client disconnects (6 regression tests);
2. **admission control** — a new tactic *bound concurrency / bound queue size* (Bass: manage resources):
   at most 25 requests in flight (below 40 threads and 30 connections); excess requests wait FIFO on the event
   loop and get `503 SERVICE_BUSY` after 5 s; `/api/health` is never queued (4 tests). Pool sized explicitly
   (20 + 10, 10 s timeout).

**Interpretation of run 3.** The system is now **stable under overload** (0.18 % errors, health answering
throughout, nothing stuck), but the latency target is **not met**. The limit is **capacity, not query cost**:
one Core Backend process (one Python interpreter) served ≈ 77 req/s, while 200 users with 0.5 s think time
offer ≈ 140 req/s (Little's law: 200 / (0.5 s + response time)). Requests therefore queue in front of the
backend and the queue time dominates the 15 ms service time. QAS-1 was rated **not an ASR** in M1 because it can
be met with standard techniques; the next ones are: (a) **more Core Backend processes** (`uvicorn --workers N`,
or more replicas behind Nginx) — the orchestrator stays the only status writer because writes go through the
same database transactions, and the event listener/watchdog are already safe to run more than once
(idempotent handlers, `SKIP LOCKED`); (b) caching the "latest results" page for a few seconds; (c) a load
generator on a separate machine (here it competed with the system for the same CPU).
**Sensitivity point:** latency at 200 users is sensitive to the number of backend processes and to
`MAX_INFLIGHT_REQUESTS`; **trade-off:** admission control trades a small rate of fast `503`s for never hanging
(availability over latency under overload). Both go into the M4 ATAM.
