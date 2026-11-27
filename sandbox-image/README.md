# Test Sandbox image

`python:3.12-slim` + `pytest` only, non-root user `sandbox` (uid 10001). Built once by the
`sandbox-image` service in `docker-compose.yml` as `testpilot-sandbox:latest`; the Runner Worker starts
**one short-lived container per run** from it (ASR-1, ADR-003, pattern P6).

Restrictions applied by the worker at run time (see `runner-worker/worker/sandbox.py`):

| Control | Value | Tactic |
|---|---|---|
| Network | `network_mode=none` | T8, QAS-3 (no exfiltration, no reaching other containers) |
| File system | read-only root FS; only `/work` (anonymous volume) and `/tmp` (tmpfs, 64 MB) writable | T8 |
| User | `sandbox` (uid 10001), `cap_drop=ALL`, `no-new-privileges` | T8 |
| CPU / memory / processes | `nano_cpus` from job limits, `mem_limit` = `memswap_limit`, `pids_limit=128` | T11 |
| Time | killed by the worker at `limits.timeSeconds` (outside the test process) | T13 |
| Lifetime | container + its volume removed after every run | T5 |

Build alone: `docker build -t testpilot-sandbox:latest sandbox-image`
