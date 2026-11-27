"""QAS-1 (Performance, not an ASR): latest results load fast under concurrent use.

Method: --users concurrent clients (each logged in) repeatedly request the latest results of the seeded
project (GET /projects/{id}/executions, first page) and open one of those executions
(GET /executions/{id}) for --minutes. Latency is measured client side, end to end through Nginx.
Targets: p95 <= 500 ms and p99 <= 1 s, error rate reported (target load: 200 users, 15 minutes).

Run:  python evidence/qas1_retrieval/load.py --project-id <PROJECT_ID> --users 200 --minutes 15
"""

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.tp import Api, base_args, percentile, save_result, verdict  # noqa: E402


def main() -> int:
    p = base_args(__doc__.splitlines()[0])
    p.add_argument("--project-id", type=int, required=True)
    p.add_argument("--users", type=int, default=200)
    p.add_argument("--minutes", type=float, default=15.0)
    p.add_argument("--think", type=float, default=0.5, help="pause between a user's requests (s)")
    args = p.parse_args()

    token = Api(args.base_url).login("dev").token
    stop_at = time.monotonic() + args.minutes * 60
    lat: list[float] = []
    errors: list[str] = []
    lock = threading.Lock()

    def user():
        c = Api(args.base_url, timeout=10)
        c.token = token
        latest: str | None = None
        while time.monotonic() < stop_at:
            for path in (
                f"/projects/{args.project_id}/executions?page=1&size=20",
                f"/executions/{latest}" if latest else None,
            ):
                if path is None:
                    continue
                t0 = time.perf_counter()
                try:
                    r = c.call("GET", path)
                    dt = time.perf_counter() - t0
                    with lock:
                        if r.status_code == 200:
                            lat.append(dt)
                        else:
                            errors.append(str(r.status_code))
                    if r.status_code == 200 and "items" in r.json() and r.json()["items"]:
                        latest = r.json()["items"][0]["executionId"]
                except Exception as e:  # noqa: BLE001
                    with lock:
                        errors.append(type(e).__name__)
                time.sleep(args.think)

    threads = [threading.Thread(target=user, daemon=True) for _ in range(args.users)]
    for t in threads:
        t.start()
        time.sleep(0.01)  # ramp up
    for t in threads:
        t.join()

    n = len(lat) + len(errors)
    p95, p99 = percentile(lat, 95), percentile(lat, 99)
    err_rate = len(errors) / n if n else 1.0
    met = p95 is not None and p95 <= 0.5 and p99 <= 1.0 and err_rate < 0.01
    print(f"requests {n}, errors {len(errors)} ({err_rate:.2%}); p50 {percentile(lat, 50)} s, p95 {p95} s, p99 {p99} s")
    v = verdict(met, f"p95 {p95 and round(p95 * 1000)} ms, p99 {p99 and round(p99 * 1000)} ms at {args.users} users")
    save_result(
        "qas1_retrieval",
        args,
        {
            "qas": "QAS-1",
            "verdict": v,
            "users": args.users,
            "minutes": args.minutes,
            "requests": n,
            "errors": len(errors),
            "errorRate": err_rate,
            "errorKinds": sorted(set(errors)),
            "latencySeconds": {"p50": percentile(lat, 50), "p95": p95, "p99": p99, "max": max(lat, default=None)},
            "throughputPerSecond": n / (args.minutes * 60),
            "target": "p95 <= 500 ms, p99 <= 1 s",
        },
    )
    return 0 if met else 1


if __name__ == "__main__":
    raise SystemExit(main())
