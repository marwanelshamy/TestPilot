"""QAS-7 (Reliability, ASR-3): an unapproved or interrupted execution never produces a misleading pass.

Part A — approval gate (needs only the backend):
    N run requests for tests that are DRAFT, REJECTED, or edited after approval.
    Target: 100 % answered 409 TEST_NOT_APPROVED and no execution record created.
Part B — runner crash (needs --compose):
    N times: start a slow test (sleeps 20 s), wait until RUNNING, `docker kill` the Runner Worker
    containers, restart them. Target: 100 % end in a non-passing terminal state, traceable to the
    execution ID with runner evidence; detection time is reported.
Part C — invalid output: a test that exits the interpreter before pytest writes its report.
    Target: never PASSED.

Run:  python evidence/qas7_reliability/run.py --compose --crashes 10
      python evidence/qas7_reliability/run.py --only-approval        # Part A only (no Docker needed)
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.tp import Api, base_args, compose, compose_containers, docker, parse_ts, save_result, verdict  # noqa: E402

GOOD = "def test_ok():\n    assert 1 + 1 == 2\n"
SLOW = "import time\n\ndef test_slow():\n    time.sleep(20)\n    assert True\n"


def part_a(api: Api, n: int) -> dict:
    pid = api.new_project("QAS-7 approval gate")
    draft = api.ok("POST", f"/projects/{pid}/tests", {"title": "draft", "testType": "NORMAL", "testCode": GOOD})["id"]
    rejected = api.ok("POST", f"/projects/{pid}/tests", {"title": "rejected", "testType": "NORMAL", "testCode": GOOD})[
        "id"
    ]
    api.ok("POST", f"/tests/{rejected}/reject", {"version": 1})
    edited = api.approved_test(pid, GOOD, "edited after approval")
    api.ok("PUT", f"/tests/{edited}", {"title": "changed after approval"})
    good = api.approved_test(pid, GOOD, "approved")
    kinds = [
        ("draft", [draft]),
        ("rejected", [rejected]),
        ("edited_after_approval", [edited]),
        ("approved_plus_draft", [good, draft]),
    ]
    before = api.ok("GET", f"/projects/{pid}/executions")["total"]
    attempts, rejected_ok = [], 0
    for i in range(n):
        kind, ids = kinds[i % len(kinds)]
        r = api.call("POST", "/executions", {"projectId": pid, "testCaseIds": ids})
        code = r.json().get("error", {}).get("code") if r.status_code >= 400 else None
        ok = r.status_code == 409 and code == "TEST_NOT_APPROVED"
        rejected_ok += ok
        attempts.append({"kind": kind, "status": r.status_code, "code": code, "ok": ok})
    created = api.ok("GET", f"/projects/{pid}/executions")["total"] - before
    print(f"Part A: {rejected_ok}/{n} rejected with 409 TEST_NOT_APPROVED; executions created: {created}")
    return {
        "requests": n,
        "rejected": rejected_ok,
        "executionsCreated": created,
        "met": rejected_ok == n and created == 0,
        "attempts": attempts,
    }


def part_b(api: Api, n: int) -> dict:
    pid = api.new_project("QAS-7 runner crash")
    tid = api.approved_test(pid, SLOW, "slow test")
    runs = []
    for i in range(n):
        ex_id = api.start_run(pid, [tid])
        ex = api.wait_status(ex_id, {"RUNNING"}, timeout=60)
        if ex["status"] != "RUNNING":
            runs.append({"executionId": ex_id, "error": f"never RUNNING ({ex['status']})", "ok": False})
            continue
        time.sleep(2)
        killed_at = time.time()
        for c in compose_containers("runner-worker"):
            docker("kill", c)  # crash every worker: no healthy worker can finish this run
        # Keep workers down until the orchestrator's watchdog decides. Restarting at once would let RabbitMQ
        # redeliver the job and a healthy worker re-run it legitimately, which would hide the crash path.
        ex = api.wait_terminal(ex_id, timeout=120)
        compose("up", "-d", "runner-worker")  # the redelivered job's late result must be ignored
        finished = parse_ts(ex["finishedAt"])
        detect = finished.timestamp() - killed_at if finished else None
        ok = ex["status"] != "PASSED" and ex["status"] in {"INTERRUPTED", "FAILED"} and bool(api.logs(ex_id))
        runs.append(
            {
                "executionId": ex_id,
                "status": ex["status"],
                "reason": ex["terminationReason"],
                "detectSeconds": detect,
                "ok": ok,
            }
        )
        print(
            f"  crash {i + 1}/{n}: {ex['status']} {ex['terminationReason']} detected after "
            f"{'' if detect is None else f'{detect:.1f}'} s"
        )
    non_passing = sum(r["ok"] for r in runs)
    return {"crashes": n, "nonPassingTerminal": non_passing, "met": non_passing == n, "runs": runs}


def part_c(api: Api) -> dict:
    pid = api.new_project("QAS-7 invalid output")
    tid = api.approved_test(pid, "import os\n\ndef test_x():\n    os._exit(0)\n", "exits before report")
    ex = api.wait_terminal(api.start_run(pid, [tid]), timeout=120)
    print(f"Part C: interpreter exit before report -> {ex['status']} {ex['terminationReason']}")
    return {"status": ex["status"], "reason": ex["terminationReason"], "met": ex["status"] != "PASSED"}


def main() -> int:
    p = base_args(__doc__.splitlines()[0])
    p.add_argument("--approval-requests", type=int, default=40)
    p.add_argument("--crashes", type=int, default=10)
    p.add_argument("--only-approval", action="store_true")
    args = p.parse_args()
    api = Api(args.base_url).login("dev")

    result = {"qas": "QAS-7", "partA_approvalGate": part_a(api, args.approval_requests)}
    if not args.only_approval:
        result["partC_invalidOutput"] = part_c(api)
        if args.compose:
            result["partB_runnerCrash"] = part_b(api, args.crashes)
        else:
            print("Part B skipped (needs --compose to kill Runner Worker containers)")
    met = all(v["met"] for k, v in result.items() if k.startswith("part"))
    result["verdict"] = verdict(
        met,
        "QAS-7 parts run: "
        + ", ".join(
            f"{k.split('_')[0]}={'met' if v['met'] else 'NOT met'}" for k, v in result.items() if k.startswith("part")
        ),
    )
    save_result("qas7_reliability", args, result)
    return 0 if met else 1


if __name__ == "__main__":
    raise SystemExit(main())
