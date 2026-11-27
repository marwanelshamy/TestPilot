"""Sandbox isolation settings (QAS-3) and the Docker driver's behaviour, with a fake Docker client."""

import io
import tarfile

import pytest
import requests

from worker.config import WorkerSettings
from worker.sandbox import (
    PYTEST_CMD,
    DockerSandbox,
    build_test_files,
    container_options,
    make_tar,
    read_single_file_from_tar,
)

SETTINGS = WorkerSettings(sandbox_image="testpilot-sandbox:latest", kill_grace_seconds=0)


# ------------------------------------------------------------- isolation options
def test_container_is_locked_down(job):
    o = container_options(job, SETTINGS)
    assert o["network_mode"] == "none"  # no network at all
    assert o["read_only"] is True  # read-only root FS
    assert o["user"] == "sandbox"  # non-root
    assert o["cap_drop"] == ["ALL"] and "no-new-privileges:true" in o["security_opt"]
    assert o["mem_limit"] == o["memswap_limit"] == "256m"  # memory limit without swap escape
    assert o["nano_cpus"] == 1_000_000_000 and o["pids_limit"] == 128  # CPU + fork-bomb limits
    assert "noexec" in o["tmpfs"]["/tmp"]
    assert "volumes" not in o and "privileged" not in o  # nothing from the host is mounted
    assert o["command"] == PYTEST_CMD and "--junitxml=/work/report.xml" in PYTEST_CMD


def test_test_files_use_the_agreed_names(job):
    assert sorted(build_test_files(job)) == ["tests/test_tc_101_v2.py", "tests/test_tc_102_v1.py"]


def test_tar_round_trip_and_size_limit():
    tar = make_tar({"report.xml": "<ok/>"})
    assert read_single_file_from_tar([tar], 100) == "<ok/>"
    with pytest.raises(ValueError):
        read_single_file_from_tar([make_tar({"report.xml": "x" * 500})], 100)


# ------------------------------------------------------------- fake Docker client
class NotFound(Exception):
    pass


class FakeContainer:
    def __init__(self, behaviour: str):
        self.behaviour = behaviour
        self.calls: list[str] = []
        self.attrs = {"State": {"OOMKilled": behaviour == "oom"}}
        self.files: dict[str, bytes] = {}

    def put_archive(self, path, data):
        self.calls.append("put_archive")
        with tarfile.open(fileobj=io.BytesIO(data)) as t:
            self.files = {m.name: t.extractfile(m).read() for m in t.getmembers()}
        return True

    def start(self):
        self.calls.append("start")

    def wait(self, timeout=None):
        self.calls.append("wait")
        if self.behaviour == "hang" and "kill" not in self.calls:
            raise requests.exceptions.ReadTimeout()
        return {"StatusCode": {"ok": 1, "oom": 137, "hang": 137, "noreport": 2}[self.behaviour]}

    def kill(self):
        self.calls.append("kill")

    def reload(self):
        pass

    def logs(self, stdout=True, stderr=True):
        return b"1 passed, 1 failed" if stdout else b""

    def get_archive(self, path):
        import docker.errors

        if self.behaviour in ("noreport", "hang"):
            raise docker.errors.NotFound("no report")
        return [make_tar({"report.xml": '<testsuites tests="2"/>'})], {}

    def remove(self, force=False, v=False):
        self.calls.append(f"remove(force={force},v={v})")


class FakeClient:
    def __init__(self, behaviour="ok", create_error=None):
        self.container = FakeContainer(behaviour)
        self.create_error = create_error
        self.created_with: dict | None = None
        self.containers = self

    def create(self, **kw):
        if self.create_error:
            raise self.create_error
        self.created_with = kw
        return self.container


def test_completed_run_collects_report_and_cleans_up(job):
    client = FakeClient("ok")
    r = DockerSandbox(SETTINGS, client).run(job)
    assert (r.outcome, r.exit_code) == ("COMPLETED", 1)
    assert r.junit_xml == '<testsuites tests="2"/>' and "1 failed" in r.stdout
    assert set(client.container.files) == {"tests/test_tc_101_v2.py", "tests/test_tc_102_v1.py"}
    assert client.container.calls[-1] == "remove(force=True,v=True)"


def test_hanging_test_is_killed_and_reported_as_timeout(job):
    client = FakeClient("hang")
    r = DockerSandbox(SETTINGS, client).run(job)
    assert r.outcome == "TIMEOUT" and r.exit_code is None
    assert "kill" in client.container.calls and client.container.calls[-1].startswith("remove")


def test_memory_kill_is_resource_limit(job):
    r = DockerSandbox(SETTINGS, FakeClient("oom")).run(job)
    assert r.outcome == "RESOURCE_LIMIT"


def test_missing_report_is_explained(job):
    r = DockerSandbox(SETTINGS, FakeClient("noreport")).run(job)
    assert r.outcome == "COMPLETED" and r.junit_xml is None and r.error_detail == "no JUnit report produced"


def test_docker_failure_is_error_not_pass(job):
    import docker.errors

    r = DockerSandbox(SETTINGS, FakeClient(create_error=docker.errors.ImageNotFound("no image"))).run(job)
    assert r.outcome == "ERROR" and "ImageNotFound" in r.error_detail
