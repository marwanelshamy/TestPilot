"""C4 L3: Job Publisher — sends ExecutionRequested (contract I4) to the broker.

Port + adapters:
  * JobPublisher        — the interface the orchestrator depends on.
  * LogJobPublisher     — default until the AMQP adapter exists; logs the message (runs stay QUEUED).
  * InMemoryJobPublisher— used by tests; records messages, can simulate a broker outage.
  * AMQP adapter        — **Member 2 (Phase 2/4)**: persistent message on queue `execution.requests`
                          with publisher confirms; raise PublishFailed if the broker does not confirm.
"""

import json
import logging
from typing import Protocol

from app.core.messages import ExecutionRequested

log = logging.getLogger(__name__)


class PublishFailed(Exception):
    pass


class JobPublisher(Protocol):
    def publish(self, message: ExecutionRequested) -> None:
        """Must raise PublishFailed if the message was not durably accepted by the broker."""


class LogJobPublisher:
    def publish(self, message: ExecutionRequested) -> None:
        log.info("ExecutionRequested (no broker configured): %s", message.model_dump_json(exclude={"tests"}))


class InMemoryJobPublisher:
    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.fail = False

    def publish(self, message: ExecutionRequested) -> None:
        if self.fail:
            raise PublishFailed("broker unavailable (simulated)")
        self.messages.append(json.loads(message.model_dump_json()))
