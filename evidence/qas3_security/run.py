"""QAS-3 (Security, ASR-1): untrusted test code cannot escape the Test Sandbox.

Method: each case is a pytest test that PASSES ONLY IF ITS ATTACK SUCCEEDS. It is submitted through the
normal workflow (create -> approve -> run). The architecture meets QAS-3 when every attack ends NOT PASSED
(FAILED = attack blocked inside the sandbox, INTERRUPTED = sandbox killed/contained) and the control test
PASSES (proves the runner really executes code). The infinite loop must be stopped within limit + 5 s.

Run (integrated system):  python evidence/qas3_security/run.py --base-url http://127.0.0.1:8080/api
"""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.tp import Api, base_args, parse_ts, save_result, verdict  # noqa: E402

MARKER = f"TP_SECRET_MARKER_{uuid.uuid4().hex}"

CASES: list[tuple[str, str, str]] = [
    # (name, what it tries, test code)
    ("control_benign", "normal test must PASS", "def test_ok():\n    assert 2 * 3 == 6\n"),
    ("read_shadow", "read a protected system file", "def test_attack():\n    assert open('/etc/shadow').read()\n"),
    (
        "docker_socket",
        "reach the Docker daemon (host takeover)",
        "import os\n\ndef test_attack():\n    assert os.path.exists('/var/run/docker.sock')\n",
    ),
    (
        "network_internet",
        "open a connection to the internet",
        "import socket\n\ndef test_attack():\n    socket.create_connection(('1.1.1.1', 53), timeout=3).close()\n",
    ),
    (
        "network_database",
        "reach PostgreSQL (other projects' data)",
        "import socket\n\ndef test_attack():\n    socket.create_connection(('postgres', 5432), timeout=3).close()\n",
    ),
    (
        "network_broker",
        "reach RabbitMQ (forge results)",
        "import socket\n\ndef test_attack():\n    socket.create_connection(('rabbitmq', 5672), timeout=3).close()\n",
    ),
    ("run_as_root", "run as root", "import os\n\ndef test_attack():\n    assert os.geteuid() == 0\n"),
    (
        "secrets_in_env",
        "read service secrets from the environment",
        "import os\n\nKEYS = ['DATABASE_URL', 'AMQP_URL', 'JWT_SECRET', 'ANTHROPIC_API_KEY', 'POSTGRES_PASSWORD',"
        " 'RABBITMQ_PASSWORD', 'LLM_API_KEY']\n\ndef test_attack():\n    assert any(k in os.environ for k in KEYS)\n",
    ),
    (
        "write_system_dir",
        "modify the image outside /work",
        "def test_attack():\n    open('/usr/local/lib/tp_owned.txt', 'w').write('x')\n",
    ),
    (
        "fork_bomb",
        "start 500 processes",
        "import subprocess, sys\n\ndef test_attack():\n    procs = [subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'])"
        " for _ in range(500)]\n    assert len(procs) == 500\n",
    ),
    (
        "memory_bomb",
        "allocate 2 GB",
        "def test_attack():\n    data = bytearray(2 * 1024 ** 3)\n    assert len(data) > 0\n",
    ),
    (
        "fake_pass_exit",
        "fake a pass with os._exit(0) before pytest writes its report",
        "import os\n\ndef test_attack():\n    os._exit(0)\n",
    ),
    (
        "plant_marker",
        "leave data behind for the next run (setup for cross_run_leak)",
        f"def test_plant():\n    open('/work/{MARKER}.txt', 'w').write('{MARKER}')\n    open('/tmp/{MARKER}.txt', 'w').write('x')\n",
    ),
    (
        "cross_run_leak",
        "read data left by a previous run / project",
        "import os\n\ndef test_attack():\n    found = [f for d in ('/work', '/tmp') for f in os.listdir(d) if '"
        + MARKER
        + "' in f]\n"
        "    assert found\n",
    ),
    (
        "infinite_loop",
        "run forever (must be killed at the time limit)",
        "def test_attack():\n    while True:\n        pass\n",
    ),
]

# plant_marker is a helper step: it may pass (it only writes inside its own sandbox)
EXPECT_PASS = {"control_benign", "plant_marker"}


def main() -> int:
    args = base_args(__doc__.splitlines()[0]).parse_args()
    api = Api(args.base_url, timeout=60).login("dev")
    # cross_run_leak runs in a DIFFERENT project from plant_marker (cross-project check)
    projects = {
        "A": api.new_project(f"QAS-3 security A {MARKER[-6:]}"),
        "B": api.new_project(f"QAS-3 security B {MARKER[-6:]}"),
    }

    rows, breaches = [], []
    for name, intent, code in CASES:
        pid = projects["B"] if name == "cross_run_leak" else projects["A"]
        tid = api.approved_test(pid, code, title=f"qas3 {name}")
        ex = api.wait_terminal(api.start_run(pid, [tid]), timeout=180)
        started, finished = parse_ts(ex["startedAt"]), parse_ts(ex["finishedAt"])
        secs = (finished - started).total_seconds() if started and finished else None
        logs = api.logs(ex["executionId"])
        row = {
            "case": name,
            "attempt": intent,
            "status": ex["status"],
            "reason": ex["terminationReason"],
            "testResult": ex["tests"][0]["resultStatus"] if ex["tests"] else None,
            "runSeconds": secs,
            "executionId": ex["executionId"],
            "failure": (ex["tests"][0].get("failureMessage") or "")[:200] if ex["tests"] else "",
        }
        expected_pass = name in EXPECT_PASS
        ok = (ex["status"] == "PASSED") if expected_pass else (ex["status"] in {"FAILED", "INTERRUPTED"})
        if name == "infinite_loop":
            ok = ok and ex["status"] == "INTERRUPTED" and secs is not None and secs <= 30 + 5
        if MARKER in logs and name not in ("plant_marker", "cross_run_leak"):
            ok = False  # marker must never show up in another run's evidence
        row["ok"] = ok
        rows.append(row)
        if not ok:
            breaches.append(name)
        print(
            f"{'ok ' if ok else 'BAD'} {name:<18} {ex['status']:<11} {ex['terminationReason'] or '':<15} "
            f"{'' if secs is None else f'{secs:5.1f}s'}  {row['failure'][:70]}"
        )

    met = not breaches
    v = verdict(
        met,
        f"{len(rows) - len(breaches)}/{len(rows)} security cases behaved as required"
        + (f"; failing: {', '.join(breaches)}" if breaches else ""),
    )
    save_result(
        "qas3_security",
        args,
        {"qas": "QAS-3", "verdict": v, "cases": rows, "target": "all attacks not PASSED; 30 s loop killed within 35 s"},
    )
    return 0 if met else 1


if __name__ == "__main__":
    raise SystemExit(main())
