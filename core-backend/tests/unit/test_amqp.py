"""Phase 4 AMQP wiring (Member 2): publisher (R5), event listener (R8) and topology conformance.

Uses fake pika objects; the real-broker check is the E2E test in Docker (tests/e2e)."""

import importlib.util
import json
import uuid

import pika.exceptions
import pytest

from app.api.listeners.execution_events import ACK, REJECT, REQUEUE, ExecutionEventListener, handle_event
from app.core.messages import ExecutionRequested, Limits, RequestedTest
from app.integration import amqp_topology
from app.integration.amqp_publisher import AmqpJobPublisher
from app.integration.job_publisher import PublishFailed
from tests.conftest import REPO_ROOT, finished, heartbeat, junit, make_approved_test


# ---------------------------------------------------------------- topology must match the Runner Worker's
def test_topology_identical_to_runner_worker():
    path = REPO_ROOT / "runner-worker" / "worker" / "topology.py"
    spec = importlib.util.spec_from_file_location("runner_topology", path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    assert runner.QUEUES == amqp_topology.QUEUES
    assert (runner.REQUESTS_QUEUE, runner.EVENTS_QUEUE) == (amqp_topology.REQUESTS_QUEUE, amqp_topology.EVENTS_QUEUE)


# ---------------------------------------------------------------- publisher
class FakeChannel:
    def __init__(self, fail_with=None):
        self.is_open = True
        self.fail_with = fail_with
        self.published, self.declared, self.confirms = [], [], False

    def confirm_delivery(self):
        self.confirms = True

    def queue_declare(self, queue, durable, arguments):
        self.declared.append((queue, durable, arguments))

    def basic_publish(self, **kw):
        if self.fail_with:
            raise self.fail_with
        self.published.append(kw)


class FakeConnection:
    def __init__(self, channel):
        self.ch, self.is_open = channel, True

    def channel(self):
        return self.ch

    def close(self):
        self.is_open = False


def job() -> ExecutionRequested:
    return ExecutionRequested(
        executionId=uuid.uuid4(),
        projectId=1,
        tests=[RequestedTest(testCaseId=1, testCaseVersion=1, testCode="def test_a():\n    pass\n")],
        limits=Limits(timeSeconds=30, cpu=1, memoryMb=256),
    )


def test_publishes_persistent_confirmed_message_to_requests_queue():
    ch = FakeChannel()
    AmqpJobPublisher("amqp://guest:guest@x:5672/", connect=lambda: FakeConnection(ch)).publish(job())
    assert ch.confirms is True
    assert [q for q, durable, _ in ch.declared] == list(amqp_topology.QUEUES) and all(d for _, d, _ in ch.declared)
    kw = ch.published[0]
    assert kw["routing_key"] == "execution.requests" and kw["exchange"] == "" and kw["mandatory"] is True
    assert kw["properties"].delivery_mode == 2 and kw["properties"].content_type == "application/json"
    assert json.loads(kw["body"])["schemaVersion"] == 1


@pytest.mark.parametrize("error", [pika.exceptions.NackError([]), pika.exceptions.UnroutableError([])])
def test_broker_refusal_is_publish_failed(error):
    pub = AmqpJobPublisher("amqp://x/", connect=lambda: FakeConnection(FakeChannel(fail_with=error)))
    with pytest.raises(PublishFailed):
        pub.publish(job())


def test_reconnects_once_then_gives_up():
    attempts = []

    def connect():
        attempts.append(1)
        raise pika.exceptions.AMQPConnectionError("down")

    with pytest.raises(PublishFailed):
        AmqpJobPublisher("amqp://x/", connect=connect).publish(job())
    assert len(attempts) == 2


def test_stale_connection_is_replaced():
    channels = [FakeChannel(fail_with=pika.exceptions.StreamLostError("lost")), FakeChannel()]
    pub = AmqpJobPublisher("amqp://x/", connect=lambda: FakeConnection(channels.pop(0)))
    pub.publish(job())  # first channel dies, second one delivers
    assert channels == []


# ---------------------------------------------------- listener: message handling against the real orchestrator
def test_listener_drives_the_orchestrator(client, dev, project_id, requirement_id, publisher, settings):
    t = make_approved_test(client, dev, project_id, requirement_id)
    ex_id = client.post(
        "/api/executions", headers=dev, json={"projectId": project_id, "testCaseIds": [t["testCaseId"]]}
    ).json()["executionId"]

    assert handle_event(json.dumps(heartbeat(ex_id)).encode(), publisher, settings) == ACK
    assert client.get(f"/api/executions/{ex_id}", headers=dev).json()["status"] == "RUNNING"

    fin = finished(ex_id, junitXml=junit([(t["testCaseId"], 1, "pass")]))
    assert handle_event(json.dumps(fin).encode(), publisher, settings) == ACK
    assert client.get(f"/api/executions/{ex_id}", headers=dev).json()["status"] == "PASSED"
    assert handle_event(json.dumps(fin).encode(), publisher, settings) == ACK  # duplicate: ignored, acked


@pytest.mark.parametrize(
    "body",
    [b"not json", b"[]", json.dumps({"type": "Nope"}).encode(), json.dumps({"type": "ExecutionFinished"}).encode()],
)
def test_invalid_events_are_rejected_to_dlq(app, publisher, settings, body):
    assert handle_event(body, publisher, settings) == REJECT


def test_unexpected_error_requeues(app, publisher, settings, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr("app.services.orchestrator.ExecutionOrchestrator.on_heartbeat", boom)
    assert handle_event(json.dumps(heartbeat(uuid.uuid4())).encode(), publisher, settings) == REQUEUE


def test_ack_reject_nack_map_to_amqp_calls(app, publisher, settings, monkeypatch):
    calls = []

    class Ch:
        def basic_ack(self, tag):
            calls.append(("ack", tag))

        def basic_reject(self, tag, requeue):
            calls.append(("reject", tag, requeue))

        def basic_nack(self, tag, requeue):
            calls.append(("nack", tag, requeue))

    lst = ExecutionEventListener(settings, publisher, connect=lambda: None)
    method = type("M", (), {"delivery_tag": 7})()
    for action in (ACK, REJECT, REQUEUE):
        monkeypatch.setattr("app.api.listeners.execution_events.handle_event", lambda *a, _x=action: _x)
        lst._on_message(Ch(), method, None, b"{}")
    assert calls == [("ack", 7), ("reject", 7, False), ("nack", 7, True)]
