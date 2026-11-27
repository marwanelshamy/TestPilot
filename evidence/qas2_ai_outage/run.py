"""QAS-2 (Availability, ASR-2): the core keeps working while the AI provider is down.

Method (needs --compose): measure a baseline, then `docker compose stop ai-service` for --minutes and
continuously exercise the unaffected core functions (read project, requirements, tests, runs, coverage,
risks; add a manual test). In parallel, call "generate tests" every --ai-every seconds and time how long
the AI error takes to reach the user. Finally restart the service and check that AI works again.

Targets: >= 99 % of core requests succeed during the outage; every AI request gets an actionable
503 AI_UNAVAILABLE within (AI_CLIENT_TIMEOUT_SECONDS + 3 s) — and immediately once the breaker is open.

Run:  python evidence/qas2_ai_outage/run.py --compose --minutes 30      (M1 target duration)
      python evidence/qas2_ai_outage/run.py --compose --minutes 2       (quick check)
"""

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.tp import Api, base_args, compose, percentile, save_result, verdict  # noqa: E402

GOOD = "def test_ok():\n    assert True\n"


def main() -> int:
    p = base_args(__doc__.splitlines()[0])
    p.add_argument("--minutes", type=float, default=2.0)
    p.add_argument("--ai-every", type=float, default=10.0)
    p.add_argument("--ai-timeout", type=float, default=60.0, help="AI_CLIENT_TIMEOUT_SECONDS of the Core Backend")
    args = p.parse_args()
    if not args.compose:
        print("QAS-2 needs --compose (it stops the ai-service container).")
        return 2

    api = Api(args.base_url, timeout=args.ai_timeout + 30).login("dev")
    pid = api.new_project("QAS-2 AI outage")
    rid = api.new_requirement(pid, "add(a, b) returns the sum")
    tid = api.approved_test(pid, GOOD, "existing test", [rid])
    ex_id = api.wait_terminal(api.start_run(pid, [tid]), timeout=120)["executionId"]
    baseline = api.call("POST", f"/projects/{pid}/tests/generate", {"requirementId": rid}).status_code
    print(f"baseline: generate -> {baseline} (expected 201)")

    core_calls = [
        ("GET", f"/projects/{pid}", None),
        ("GET", f"/projects/{pid}/requirements", None),
        ("GET", f"/projects/{pid}/tests", None),
        ("GET", f"/projects/{pid}/executions", None),
        ("GET", f"/executions/{ex_id}", None),
        ("GET", f"/executions/{ex_id}/logs", None),
        ("GET", f"/projects/{pid}/coverage", None),
        ("GET", f"/projects/{pid}/risks", None),
        ("POST", f"/projects/{pid}/tests", {"title": "manual during outage", "testType": "NORMAL", "testCode": GOOD}),
    ]

    compose("stop", "ai-service")
    print(f"ai-service stopped; exercising the core for {args.minutes} min ...")
    stop_at = time.monotonic() + args.minutes * 60
    core = {"ok": 0, "fail": 0, "failures": []}
    ai: list[dict] = []

    def ai_probe():
        ai_api = Api(args.base_url, timeout=args.ai_timeout + 30)
        ai_api.token = api.token
        while time.monotonic() < stop_at:
            t0 = time.monotonic()
            r = ai_api.call("POST", f"/projects/{pid}/tests/generate", {"requirementId": rid})
            body = r.json() if r.content else {}
            err = body.get("error", {})
            ai.append(
                {
                    "status": r.status_code,
                    "code": err.get("code"),
                    "reason": (err.get("details") or {}).get("reason"),
                    "seconds": time.monotonic() - t0,
                }
            )
            time.sleep(args.ai_every)

    t = threading.Thread(target=ai_probe, daemon=True)
    t.start()
    i = 0
    while time.monotonic() < stop_at:
        method, path, body = core_calls[i % len(core_calls)]
        i += 1
        try:
            r = api.call(method, path, body)
            good = r.status_code < 400
        except Exception as e:  # noqa: BLE001
            good, r = False, None
            core["failures"].append(f"{method} {path}: {e}")
        if good:
            core["ok"] += 1
        else:
            core["fail"] += 1
            if r is not None:
                core["failures"].append(f"{method} {path}: {r.status_code}")
        time.sleep(0.1)
    t.join(timeout=args.ai_timeout + 30)

    compose("start", "ai-service")
    time.sleep(5)
    recovered = None
    for _ in range(12):
        recovered = api.call("POST", f"/projects/{pid}/tests/generate", {"requirementId": rid}).status_code
        if recovered == 201:
            break
        time.sleep(5)  # breaker half-opens after AI_BREAKER_RESET_SECONDS

    total = core["ok"] + core["fail"]
    rate = core["ok"] / total if total else 0.0
    ai_secs = [a["seconds"] for a in ai]
    ai_actionable = all(a["status"] == 503 and a["code"] == "AI_UNAVAILABLE" for a in ai)
    ai_fast = all(s <= args.ai_timeout + 3 for s in ai_secs)
    met = rate >= 0.99 and ai_actionable and ai_fast and bool(ai)
    print(
        f"core: {core['ok']}/{total} ok ({rate:.2%}); AI errors: {len(ai)}, max {max(ai_secs, default=0):.2f} s, "
        f"p95 {percentile(ai_secs, 95) or 0:.2f} s; recovered -> {recovered}"
    )
    v = verdict(met, f"{rate:.2%} core success during outage; AI error max {max(ai_secs, default=0):.2f} s")
    save_result(
        "qas2_ai_outage",
        args,
        {
            "qas": "QAS-2",
            "verdict": v,
            "outageMinutes": args.minutes,
            "baselineGenerate": baseline,
            "core": {
                "requests": total,
                "succeeded": core["ok"],
                "successRate": rate,
                "failures": core["failures"][:50],
            },
            "ai": {
                "requests": len(ai),
                "allActionable503": ai_actionable,
                "maxSeconds": max(ai_secs, default=None),
                "p95Seconds": percentile(ai_secs, 95),
                "reasons": sorted({str(a["reason"]) for a in ai}),
                "samples": ai,
            },
            "recoveredGenerateStatus": recovered,
            "target": ">=99% core success; AI error within AI_CLIENT_TIMEOUT+3 s",
        },
    )
    return 0 if met else 1


if __name__ == "__main__":
    raise SystemExit(main())
