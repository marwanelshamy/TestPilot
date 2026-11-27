"""Heartbeats, raw-result reporting, size caps, and the ack / reject / requeue rules for AMQP deliveries."""

import asyncio
import json
import time

from tests.conftest import job_dict, validate
from worker.main import handle_delivery
from worker.messages import MAX_JUNIT_CHARS, MAX_STREAM_CHARS, ExecutionFinished, ExecutionHeartbeat
from worker.processor import JobProcessor, build_finished
from worker.sandbox import SandboxResult


class SlowSandbox:
    def __init__(self, seconds=0.0, result=None, boom=False):
        self.seconds, self.result, self.boom = seconds, result, boom

    def run(self, job):
        time.sleep(self.seconds)
        if self.boom:
            raise RuntimeError("driver bug")
        return self.result or SandboxResult(outcome="COMPLETED", exit_code=0, junit_xml="<ok/>", stdout="ok")


class Recorder:
    def __init__(self, fail=False):
        self.sent: list = []
        self.fail = fail

    async def __call__(self, msg):
        if self.fail:
            raise ConnectionError("broker gone")
        self.sent.append(msg)


def run(coro):
    return asyncio.run(coro)


def test_heartbeats_while_running_then_finished_last(job):
    rec = Recorder()
    fin = run(JobProcessor(SlowSandbox(0.35), "w1", heartbeat_interval=0.1).process(job, rec))
    kinds = [type(m).__name__ for m in rec.sent]
    assert kinds[0] == "ExecutionHeartbeat" and kinds[-1] == "ExecutionFinished"
    assert kinds.count("ExecutionHeartbeat") >= 3  # first one + periodic ones while the sandbox runs
    assert fin.outcome == "COMPLETED" and fin.exitCode == 0
    for m in rec.sent:  # every emitted message honours contract I4
        name = "execution-heartbeat" if isinstance(m, ExecutionHeartbeat) else "execution-finished"
        validate(json.loads(m.model_dump_json()), name)


def test_driver_crash_becomes_error_outcome(job):
    rec = Recorder()
    fin = run(JobProcessor(SlowSandbox(boom=True), "w1", 1).process(job, rec))
    assert fin.outcome == "ERROR" and "driver bug" in fin.errorDetail


def test_streams_are_capped_and_flagged(job):
    r = SandboxResult(outcome="COMPLETED", exit_code=0, junit_xml="<ok/>", stdout="x" * (MAX_STREAM_CHARS + 10))
    fin = build_finished(job, r, "w1")
    assert fin.truncated and len(fin.stdout) == MAX_STREAM_CHARS


def test_oversized_report_is_dropped_not_cut(job):
    r = SandboxResult(outcome="COMPLETED", exit_code=0, junit_xml="<" + "x" * MAX_JUNIT_CHARS)
    fin = build_finished(job, r, "w1")
    assert fin.junitXml is None and "too large" in fin.errorDetail


# ------------------------------------------------------------- AMQP delivery handling
class FakeMessage:
    def __init__(self, body: bytes):
        self.body, self.message_id, self.result = body, "m1", None

    async def ack(self):
        self.result = "ack"

    async def reject(self, requeue=False):
        self.result = f"reject(requeue={requeue})"

    async def nack(self, requeue=True):
        self.result = f"nack(requeue={requeue})"


def test_valid_job_is_acked_after_finished_is_sent():
    msg, rec = FakeMessage(json.dumps(job_dict()).encode()), Recorder()
    assert run(handle_delivery(msg, JobProcessor(SlowSandbox(), "w1", 1), rec)) == "acked"
    assert msg.result == "ack" and isinstance(rec.sent[-1], ExecutionFinished)


def test_malformed_job_goes_to_dead_letter_without_running():
    sandbox = SlowSandbox(boom=True)  # would raise if it were ever called
    msg = FakeMessage(b'{"executionId": "x"}')
    assert run(handle_delivery(msg, JobProcessor(sandbox, "w1", 1), Recorder())) == "rejected"
    assert msg.result == "reject(requeue=False)"


def test_broker_failure_requeues_the_job():
    msg = FakeMessage(json.dumps(job_dict()).encode())
    assert run(handle_delivery(msg, JobProcessor(SlowSandbox(), "w1", 1), Recorder(fail=True))) == "requeued"
    assert msg.result == "nack(requeue=True)"


# ------------------------------------------------------------- broker start-up race (found in Phase 4)
def test_first_connection_is_retried_until_broker_accepts(monkeypatch):
    import aio_pika

    from worker import main as worker_main

    async def no_sleep(_):
        return None

    monkeypatch.setattr(worker_main.asyncio, "sleep", no_sleep)
    calls = []

    async def connect(url):
        calls.append(url)
        if len(calls) < 3:
            raise aio_pika.exceptions.AMQPConnectionError("Connect call failed")
        return "connection"

    assert run(worker_main.connect_with_retry(connect, "amqp://x/")) == "connection"
    assert len(calls) == 3


def test_retry_can_be_bounded(monkeypatch):
    import aio_pika
    import pytest

    from worker import main as worker_main

    async def no_sleep(_):
        return None

    monkeypatch.setattr(worker_main.asyncio, "sleep", no_sleep)

    async def connect(url):
        raise ConnectionRefusedError(111, "refused")

    with pytest.raises(OSError):
        run(worker_main.connect_with_retry(connect, "amqp://x/", attempts=2))
    _ = aio_pika  # imported for symmetry with the test above
