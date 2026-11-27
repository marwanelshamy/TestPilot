"""Shared helpers for the quality-attribute experiments and the E2E test.

Talks to the system ONLY through the public REST API (contract I1), exactly like a user would, plus
`docker compose` for fault injection. Every experiment saves a JSON result with its environment.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[2]
TERMINAL = {"PASSED", "FAILED", "INTERRUPTED", "CANCELLED"}
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "TestPilot#2026")


# ------------------------------------------------------------------ CLI
def base_args(description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description)
    # 127.0.0.1, not "localhost": on Windows "localhost" tries IPv6 first and every NEW connection waits
    # ~2 s before falling back, which shows up as fake p99 latency (seen in the Phase 3 smoke test).
    p.add_argument(
        "--base-url",
        default=os.environ.get("TESTPILOT_URL", "http://127.0.0.1:8080/api"),
        help="Public API base URL (compose: http://127.0.0.1:8080/api)",
    )
    p.add_argument(
        "--compose", action="store_true", help="allow docker compose actions (stop/kill containers) for fault injection"
    )
    p.add_argument("--label", default="", help="free text stored with the result (e.g. machine name)")
    return p


# ------------------------------------------------------------------ API client
class Api:
    def __init__(self, base_url: str, timeout: float = 30.0):
        self.http = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)
        self.token: str | None = None

    def _h(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def call(self, method: str, path: str, json_body=None) -> httpx.Response:
        return self.http.request(method, path, json=json_body, headers=self._h())

    def ok(self, method: str, path: str, json_body=None) -> dict:
        r = self.call(method, path, json_body)
        if r.status_code >= 400:
            raise RuntimeError(f"{method} {path} -> {r.status_code} {r.text[:300]}")
        return r.json() if r.content else {}

    def login(self, who: str = "dev") -> Api:
        self.token = self.ok("POST", "/auth/login", {"email": f"{who}@testpilot.local", "password": DEMO_PASSWORD})[
            "token"
        ]
        return self

    # --- workflow shortcuts (UC-1..UC-3) ---
    def new_project(self, name: str) -> int:
        return self.ok("POST", "/projects", {"name": name})["id"]

    def new_requirement(self, project_id: int, title: str = "requirement") -> int:
        return self.ok("POST", f"/projects/{project_id}/requirements", {"title": title, "description": title})["id"]

    def approved_test(self, project_id: int, code: str, title: str = "t", requirement_ids=()) -> int:
        tid = self.ok(
            "POST",
            f"/projects/{project_id}/tests",
            {"title": title, "testType": "NORMAL", "testCode": code, "requirementIds": list(requirement_ids)},
        )["id"]
        self.ok("POST", f"/tests/{tid}/approve", {"version": 1})
        return tid

    def start_run(self, project_id: int, test_ids: list[int]) -> str:
        return self.ok("POST", "/executions", {"projectId": project_id, "testCaseIds": test_ids})["executionId"]

    def wait_terminal(self, execution_id: str, timeout: float = 120, poll: float = 1.0) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            ex = self.ok("GET", f"/executions/{execution_id}")
            if ex["status"] in TERMINAL or time.monotonic() > deadline:
                return ex
            time.sleep(poll)

    def wait_status(self, execution_id: str, wanted: set[str], timeout: float = 60, poll: float = 0.5) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            ex = self.ok("GET", f"/executions/{execution_id}")
            if ex["status"] in wanted or time.monotonic() > deadline:
                return ex
            time.sleep(poll)

    def logs(self, execution_id: str) -> str:
        items = self.ok("GET", f"/executions/{execution_id}/logs?size=100")["items"]
        return "\n".join(f"[{e['evidenceType']}]\n{e['content']}" for e in items)


# ------------------------------------------------------------------ docker compose (fault injection)
def compose(*args: str, check: bool = True) -> str:
    proc = subprocess.run(["docker", "compose", *args], cwd=REPO, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f"docker compose {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def compose_containers(service: str) -> list[str]:
    return [c for c in compose("ps", "-q", service).split() if c]


def docker(*args: str) -> str:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=True).stdout


# ------------------------------------------------------------------ stats + results
def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = max(0, math.ceil(p / 100 * len(s)) - 1)
    return s[k]


def parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def environment(args) -> dict:
    env = {
        "timestamp": datetime.now(UTC).isoformat(),
        "label": getattr(args, "label", ""),
        "baseUrl": getattr(args, "base_url", ""),
        "os": platform.platform(),
        "cpuCount": os.cpu_count(),
        "python": platform.python_version(),
    }
    try:
        env["gitCommit"] = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True
        ).stdout.strip()
    except OSError:
        pass
    if getattr(args, "compose", False):
        try:
            env["dockerVersion"] = docker("version", "--format", "{{.Server.Version}}").strip()
            env["runnerWorkerReplicas"] = len(compose_containers("runner-worker"))
        except Exception as e:  # noqa: BLE001
            env["dockerError"] = str(e)
    return env


def save_result(qas_dir: str, args, result: dict) -> Path:
    out_dir = REPO / "evidence" / qas_dir / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"{stamp}.json"
    path.write_text(json.dumps({"environment": environment(args), **result}, indent=2, default=str), encoding="utf-8")
    print(f"\nresult saved: {path.relative_to(REPO)}")
    return path


def verdict(met: bool, text: str) -> str:
    line = f"{'MET' if met else 'NOT MET'}: {text}"
    print("\n" + "=" * len(line) + "\n" + line + "\n" + "=" * len(line))
    return "MET" if met else "NOT MET"
