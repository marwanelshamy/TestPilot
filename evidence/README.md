# Quality-attribute evidence (M3 §2)

Scripts that **measure** the response measures of the quality-attribute scenarios against the running
system. Plan, targets and order: [`docs/testing/test-plan.md`](../docs/testing/test-plan.md).

```bash
python -m venv evidence/.venv && evidence/.venv/Scripts/pip install -r evidence/requirements.txt
cp .env.example .env && docker compose up -d --build          # integrated system
```

| QAS | Command | Needs | Rough duration |
|---|---|---|---|
| QAS-3 security | `python evidence/qas3_security/run.py` | compose | ~3 min |
| QAS-7 reliability | `python evidence/qas7_reliability/run.py --compose --crashes 10` | compose (Part A alone: `--only-approval`, backend only) | ~10 min |
| QAS-2 AI outage | `python evidence/qas2_ai_outage/run.py --compose --minutes 30` | compose | 30 min |
| QAS-5 concurrency | `python evidence/qas5_concurrency/run.py --compose` | compose | 2–15 min |
| QAS-1 retrieval | `docker compose exec -T core-backend python - < evidence/qas1_retrieval/seed_results.py` then `python evidence/qas1_retrieval/load.py --project-id <id> --users 200 --minutes 15` | compose | 20 min |
| QAS-4 modifiability | follow `qas4_modifiability/exercise.md` | — | timed |
| QAS-6 usability | follow `qas6_usability/protocol.md` | UI | 10 sessions |

**Use `127.0.0.1`, not `localhost`, in URLs on Windows**: `localhost` adds ~2 s to every new
connection (IPv6 fallback), which corrupts latency results — found in the Phase 3 smoke test
(p99 2084 ms via `localhost` vs 87 ms via `127.0.0.1`, same server).

Use the evidence venv's Python (`evidence/.venv/Scripts/python`). Every script accepts `--base-url`
(default `http://127.0.0.1:8080/api`, through Nginx) and `--label` (e.g. the machine name).

Each run prints `MET` / `NOT MET` and saves `evidence/<qas>/results/<UTC time>.json` with the environment
(OS, CPUs, git commit, Docker version, Runner Worker replicas). Commit the result files you report; write
the interpretation with [`REPORT-TEMPLATE.md`](REPORT-TEMPLATE.md).

## Cross-boundary integration test (M3 §5)

```bash
TESTPILOT_URL=http://127.0.0.1:8080/api evidence/.venv/Scripts/python -m pytest tests/e2e -v
```
