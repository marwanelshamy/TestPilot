"""C4 L3: Execution Event Listener — inbound AMQP adapter for `execution.events` (Phase 4, Member 2). Link R8.

Runs in a background thread of the Core Backend. For every message:
  1. parse JSON and pick the model by field `type` (tactic T10). Invalid -> reject, no requeue -> DLQ.
  2. call the Execution Orchestrator (the only status writer) in a fresh DB session.
  3. ack ONLY after the orchestrator has committed. On an unexpected error -> nack + requeue
     (the quorum queue's delivery limit dead-letters a message that keeps failing).
The orchestrator handlers are idempotent, so redeliveries are safe.

This module sits in the API layer as an inbound adapter, like a REST router (M2 §3.2 layer rule 2).
"""

import json
import logging
import threading
import time
from collections.abc import Callable

import pika
import pika.exceptions
from pydantic import ValidationError

from app.core.config import Settings
from app.core.database import session_factory
from app.core.messages import ExecutionFinished, ExecutionHeartbeat
from app.integration.amqp_topology import EVENTS_QUEUE, declare_topology
from app.integration.job_publisher import JobPublisher
from app.services.orchestrator import ExecutionOrchestrator

log = logging.getLogger(__name__)

ACK, REJECT, REQUEUE = "ack", "reject", "requeue"


def handle_event(body: bytes, publisher: JobPublisher, settings: Settings) -> str:
    """Process one event body. Returns what to do with the AMQP message: ack | reject | requeue."""
    try:
        raw = json.loads(body)
        kind = raw.get("type") if isinstance(raw, dict) else None
        if kind == "ExecutionHeartbeat":
            msg = ExecutionHeartbeat.model_validate(raw)
        elif kind == "ExecutionFinished":
            msg = ExecutionFinished.model_validate(raw)
        else:
            raise ValueError(f"unknown message type {kind!r}")
    except (ValueError, ValidationError) as e:  # json.JSONDecodeError is a ValueError
        log.error("invalid execution event rejected: %s", str(e)[:300])
        return REJECT

    session = session_factory()()
    try:
        orch = ExecutionOrchestrator(session, publisher, settings)
        if isinstance(msg, ExecutionHeartbeat):
            orch.on_heartbeat(msg)
        else:
            status = orch.on_finished(msg)
            if status is not None:
                log.info("execution %s -> %s", msg.executionId, status.value)
        return ACK
    except Exception:
        session.rollback()
        log.exception("could not process event for execution %s; requeueing", msg.executionId)
        return REQUEUE
    finally:
        session.close()


class ExecutionEventListener:
    def __init__(
        self,
        settings: Settings,
        publisher: JobPublisher,
        connect: Callable[[], object] | None = None,
        retry_seconds: float = 3.0,
    ):
        self.settings = settings
        self.publisher = publisher
        self.retry_seconds = retry_seconds
        params = pika.URLParameters(settings.amqp_url)
        params.heartbeat = 30
        self._connect = connect or (lambda: pika.BlockingConnection(params))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._conn = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="execution-event-listener", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        conn = self._conn
        if conn is not None:
            try:
                conn.add_callback_threadsafe(conn.close)  # wake the consuming thread
            except Exception:  # noqa: BLE001
                pass
        if self._thread:
            self._thread.join(timeout=10)

    def _on_message(self, channel, method, properties, body) -> None:
        action = handle_event(body, self.publisher, self.settings)
        if action == ACK:
            channel.basic_ack(method.delivery_tag)
        elif action == REJECT:
            channel.basic_reject(method.delivery_tag, requeue=False)
        else:
            channel.basic_nack(method.delivery_tag, requeue=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._conn = self._connect()
                channel = self._conn.channel()
                declare_topology(channel)
                channel.basic_qos(prefetch_count=20)
                channel.basic_consume(queue=EVENTS_QUEUE, on_message_callback=self._on_message)
                log.info("listening on %s", EVENTS_QUEUE)
                channel.start_consuming()
            except (pika.exceptions.AMQPError, OSError) as e:
                if self._stop.is_set():
                    break
                log.warning("event listener disconnected (%r); retrying in %.0f s", e, self.retry_seconds)
                time.sleep(self.retry_seconds)
            finally:
                try:
                    if self._conn is not None and self._conn.is_open:
                        self._conn.close()
                except Exception:  # noqa: BLE001
                    pass
                self._conn = None
