"""QAS-5 (Scalability, ASR-4): 100 run requests within one minute are all queued, executed and finished.

Method: one project with one quick approved test; send --requests POST /executions spread evenly over
--window seconds (several clients in parallel), then poll every execution until terminal.
Measured: unique execution IDs, terminal states, queue wait = startedAt - createdAt, worker replicas.
Targets: 100 % unique IDs and terminal states; >= 95 % of jobs start within 30 s at the tested capacity.

Run:  python evidence/qas5_concurrency/run.py --compose                      (2 replicas from compose)
      docker compose up -d --scale runner-worker=4 && python ... --compose  (repeat at other capacities)
"""

import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.tp import TERMINAL, Api, base_args, parse_ts, percentile, save_result, verdict  # noqa: E402

QUICK = "def test_quick():\n    assert sum(range(10)) == 45\n"


def main() -> int:
    p = base_args(__doc__.splitlines()[0])
    p.add_argument("--requests", type=int, default=100)
    p.add_argument("--window", type=float, default=60.0)
    p.add_argument("--clients", type=int, default=10)
    p.add_argument("--max-wait", type=float, default=900.0, help="seconds to wait for all runs to finish")
    args = p.parse_args()

    api = Api(args.base_url).login("dev")
    pid = api.new_project("QAS-5 concurrency")
    tid = api.approved_test(pid, QUICK, "quick test")

    gap = args.window / args.requests
    t0 = time.monotonic()

    def submit(i: int) -> dict:
        time.sleep(max(0.0, t0 + i * gap - time.monotonic()))
        c = Api(args.base_url)
        c.token = api.token
        r = c.call("POST", "/executions", {"projectId": pid, "testCaseIds": [tid]})
        return {
            "i": i,
            "status": r.status_code,
            "executionId": r.json().get("executionId") if r.status_code == 202 else None,
            "error": None if r.status_code == 202 else r.text[:200],
        }

    with ThreadPoolExecutor(max_workers=args.clients) as pool:
        submitted = list(pool.map(submit, range(args.requests)))
    submit_secs = time.monotonic() - t0
    ids = [s["executionId"] for s in submitted if s["executionId"]]
    print(f"submitted {len(ids)}/{args.requests} accepted in {submit_secs:.1f} s; unique IDs: {len(set(ids))}")

    deadline = time.monotonic() + args.max_wait
    final: dict[str, dict] = {}
    while time.monotonic() < deadline and len(final) < len(ids):
        for ex_id in ids:
            if ex_id not in final:
                ex = api.ok("GET", f"/executions/{ex_id}")
                if ex["status"] in TERMINAL:
                    final[ex_id] = ex
        print(f"  terminal: {len(final)}/{len(ids)}", end="\r")
        time.sleep(2)
    print()

    waits = []
    for ex in final.values():
        c, s = parse_ts(ex["createdAt"]), parse_ts(ex["startedAt"])
        if c and s:
            waits.append((s - c).total_seconds())
    statuses: dict[str, int] = {}
    for ex in final.values():
        statuses[ex["status"]] = statuses.get(ex["status"], 0) + 1
    within30 = sum(w <= 30 for w in waits) / len(ids) if ids else 0
    unique_ok = len(set(ids)) == len(ids) == args.requests
    terminal_ok = len(final) == len(ids)
    met = unique_ok and terminal_ok and within30 >= 0.95
    print(
        f"statuses: {statuses}; queue wait p50 {percentile(waits, 50)} s, p95 {percentile(waits, 95)} s, "
        f"max {max(waits, default=None)} s; started within 30 s: {within30:.0%}"
    )
    v = verdict(met, f"{len(set(ids))} unique IDs, {len(final)} terminal, {within30:.0%} started within 30 s")
    save_result(
        "qas5_concurrency",
        args,
        {
            "qas": "QAS-5",
            "verdict": v,
            "requests": args.requests,
            "windowSeconds": args.window,
            "acceptedRequests": len(ids),
            "uniqueIds": len(set(ids)),
            "terminal": len(final),
            "statuses": statuses,
            "queueWaitSeconds": {
                "p50": percentile(waits, 50),
                "p95": percentile(waits, 95),
                "max": max(waits, default=None),
            },
            "startedWithin30s": within30,
            "submitSeconds": submit_secs,
            "rejectedSubmissions": [s for s in submitted if s["error"]][:20],
            "target": "100% unique + terminal; >=95% start within 30 s at the reported worker capacity",
        },
    )
    return 0 if met else 1


if __name__ == "__main__":
    raise SystemExit(main())
