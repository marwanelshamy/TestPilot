"""AMQP adapter of the Job Publisher port (Phase 4, Member 2). Link R5 of the container view.

Publishes ExecutionRequested as a PERSISTENT message on `execution.requests` with publisher confirms:
`publish()` returns only after RabbitMQ has durably accepted the message, otherwise it raises
PublishFailed — the orchestrator then rolls back the execution insert and the API answers
503 QUEUE_UNAVAILABLE (no orphan QUEUED row, ADR-009 #3).

FastAPI runs sync endpoints in a thread pool and pika's BlockingConnection is not thread-safe, so one
connection is shared behind a lock and re-opened after any failure.
"""

import logging
import threading
from collections.abc import Callable

import pika
import pika.exceptions

from app.core.messages import ExecutionRequested
from app.integration.amqp_topology import REQUESTS_QUEUE, declare_topology
from app.integration.job_publisher import PublishFailed

log = logging.getLogger(__name__)


class AmqpJobPublisher:
    def __init__(self, amqp_url: str, connect: Callable[[], object] | None = None):
        self.params = pika.URLParameters(amqp_url)
        self.params.connection_attempts = 1
        self.params.socket_timeout = 5
        self.params.blocked_connection_timeout = 5
        self._connect = connect or (lambda: pika.BlockingConnection(self.params))
        self._lock = threading.Lock()
        self._conn = None
        self._channel = None

    def _ensure_channel(self):
        if self._channel is None or not self._channel.is_open:
            self._close()
            self._conn = self._connect()
            self._channel = self._conn.channel()
            self._channel.confirm_delivery()  # basic_publish now raises if the broker does not confirm
            declare_topology(self._channel)
        return self._channel

    def _close(self) -> None:
        try:
            if self._conn is not None and self._conn.is_open:
                self._conn.close()
        except Exception:  # noqa: BLE001 — closing a broken connection may itself fail
            pass
        self._conn = self._channel = None

    def publish(self, message: ExecutionRequested) -> None:
        body = message.model_dump_json().encode()
        props = pika.BasicProperties(
            content_type="application/json",
            delivery_mode=pika.DeliveryMode.Persistent,
            message_id=str(message.messageId),
            type="ExecutionRequested",
        )
        with self._lock:
            for attempt in (1, 2):  # one reconnect: a stale connection after a broker restart is normal
                try:
                    self._ensure_channel().basic_publish(
                        exchange="", routing_key=REQUESTS_QUEUE, body=body, properties=props, mandatory=True
                    )
                    return
                except (pika.exceptions.UnroutableError, pika.exceptions.NackError) as e:
                    raise PublishFailed(f"broker did not accept the job: {type(e).__name__}") from e
                except pika.exceptions.AMQPError as e:
                    log.warning("AMQP publish failed (attempt %d): %r", attempt, e)
                    self._close()
                    if attempt == 2:
                        raise PublishFailed(f"broker unavailable: {type(e).__name__}") from e
                except OSError as e:  # DNS / socket errors before AMQP is up
                    self._close()
                    if attempt == 2:
                        raise PublishFailed(f"broker unreachable: {e}") from e

    def close(self) -> None:
        with self._lock:
            self._close()
