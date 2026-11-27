"""Test Sandbox driver (pattern P6; tactics T5, T7, T8, T11, T13).

The trusted Runner Worker NEVER executes user code itself (risk R-009). It asks the Docker daemon for a
fresh container per run, copies the approved test files in, enforces the limits from OUTSIDE the test
process, collects pytest's JUnit XML + logs, and always removes the container and its volume.
"""

import io
import logging
import tarfile
import time
from dataclasses import dataclass
from typing import Protocol

from worker.config import WorkerSettings
from worker.messages import ExecutionRequested, Outcome, test_file_name

log = logging.getLogger(__name__)

WORKDIR = "/work"
REPORT_PATH = f"{WORKDIR}/report.xml"
PYTEST_CMD = [
    "python",
    "-m",
    "pytest",
    "-q",
    "-p",
    "no:cacheprovider",
    f"--junitxml={REPORT_PATH}",
    "-o",
    "junit_family=xunit2",
    "tests",
]


@dataclass
class SandboxResult:
    outcome: Outcome
    exit_code: int | None = None
    junit_xml: str | None = None
    stdout: str = ""
    stderr: str = ""
    error_detail: str | None = None
    duration_ms: int = 0


class Sandbox(Protocol):
    def run(self, job: ExecutionRequested) -> SandboxResult: ...


# ---------------------------------------------------------------- helpers (pure, unit-tested)
def build_test_files(job: ExecutionRequested) -> dict[str, str]:
    return {f"tests/{test_file_name(t.testCaseId, t.testCaseVersion)}": t.testCode for t in job.tests}


def make_tar(files: dict[str, str], uid: int = 10001) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for path, text in files.items():
            data = text.encode("utf-8")
            info = tarfile.TarInfo(path)
            info.size, info.mode, info.uid, info.gid, info.mtime = len(data), 0o644, uid, uid, int(time.time())
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def read_single_file_from_tar(chunks, max_bytes: int) -> str | None:
    """docker get_archive() returns a tar stream; extract the one regular file, bounded in size."""
    raw = b"".join(chunks)
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r") as tar:
        for member in tar.getmembers():
            if member.isfile():
                if member.size > max_bytes:
                    raise ValueError(f"report too large ({member.size} bytes)")
                f = tar.extractfile(member)
                return f.read().decode("utf-8", errors="replace") if f else None
    return None


def container_options(job: ExecutionRequested, s: WorkerSettings) -> dict:
    """All isolation settings in one place, so tests can assert them (QAS-3 security suite)."""
    mem = f"{job.limits.memoryMb}m"
    return {
        "image": s.sandbox_image,
        "command": PYTEST_CMD,
        "user": "sandbox",
        "working_dir": WORKDIR,
        "network_mode": "none",
        "read_only": True,
        "tmpfs": {"/tmp": f"rw,noexec,nosuid,size={s.sandbox_tmpfs_mb}m"},
        "mem_limit": mem,
        "memswap_limit": mem,  # no swap: memory limit is real
        "nano_cpus": int(job.limits.cpu * 1_000_000_000),
        "pids_limit": s.sandbox_pids_limit,
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "environment": {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"},
        "labels": {"testpilot.execution": str(job.executionId), "testpilot.role": "sandbox"},
        "detach": True,
    }


# ---------------------------------------------------------------- Docker implementation
class DockerSandbox:
    def __init__(self, settings: WorkerSettings, client=None):
        import docker  # imported lazily so unit tests do not need a Docker daemon

        self.s = settings
        self.client = client or docker.from_env()

    def run(self, job: ExecutionRequested) -> SandboxResult:
        import docker.errors
        import requests.exceptions

        started = time.monotonic()
        container = None
        try:
            container = self.client.containers.create(**container_options(job, self.s))
            # /work is a volume, so this works although the root FS is read-only
            container.put_archive(WORKDIR, make_tar(build_test_files(job)))
            container.start()
            timed_out = False
            exit_code: int | None = None
            try:
                exit_code = int(
                    container.wait(timeout=job.limits.timeSeconds + self.s.kill_grace_seconds)["StatusCode"]
                )
            except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError):
                timed_out = True
                container.kill()  # T13: bounded execution time, enforced outside the test process
                try:
                    container.wait(timeout=10)
                except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError):
                    log.warning("sandbox for %s did not stop after kill", job.executionId)
            duration_ms = int((time.monotonic() - started) * 1000)
            elapsed_s = duration_ms / 1000
            container.reload()
            oom = bool(container.attrs.get("State", {}).get("OOMKilled"))
            stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
            stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
            junit, junit_err = self._read_report(container)

            if oom:
                outcome: Outcome = "RESOURCE_LIMIT"
            elif timed_out or elapsed_s > job.limits.timeSeconds + self.s.kill_grace_seconds:
                outcome = "TIMEOUT"
            else:
                outcome = "COMPLETED"
            return SandboxResult(
                outcome=outcome,
                exit_code=None if timed_out else exit_code,
                junit_xml=junit,
                stdout=stdout,
                stderr=stderr,
                error_detail=junit_err,
                duration_ms=duration_ms,
            )
        except docker.errors.DockerException as e:
            log.exception("sandbox failed for execution %s", job.executionId)
            return SandboxResult(
                outcome="ERROR",
                error_detail=f"{type(e).__name__}: {e}"[:2000],
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        finally:
            if container is not None:
                try:
                    container.remove(force=True, v=True)  # T5: removal from service, volume included
                except Exception:  # noqa: BLE001 — never let cleanup hide the result
                    log.warning("could not remove sandbox container for %s", job.executionId)

    def _read_report(self, container) -> tuple[str | None, str | None]:
        import docker.errors

        from worker.messages import MAX_JUNIT_CHARS

        try:
            stream, _ = container.get_archive(REPORT_PATH)
            return read_single_file_from_tar(stream, MAX_JUNIT_CHARS), None
        except docker.errors.NotFound:
            return None, "no JUnit report produced"
        except ValueError as e:
            return None, str(e)
