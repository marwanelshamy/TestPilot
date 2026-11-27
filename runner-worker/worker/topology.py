"""RabbitMQ topology (docs/phase1/03 §1). Declared identically by every client (idempotent).

Quorum queues give durable, replicated-ready queues and a built-in delivery limit: a message that
is redelivered more than DELIVERY_LIMIT times (poison job, crash loop) is dead-lettered to the DLQ
instead of looping forever (ASR-4, QAS-5 "every job reaches a terminal state").
"""

REQUESTS_QUEUE = "execution.requests"
EVENTS_QUEUE = "execution.events"
REQUESTS_DLQ = "execution.requests.dlq"
EVENTS_DLQ = "execution.events.dlq"
DELIVERY_LIMIT = 3


def queue_arguments(dlq: str) -> dict:
    return {
        "x-queue-type": "quorum",
        "x-delivery-limit": DELIVERY_LIMIT,
        "x-dead-letter-exchange": "",
        "x-dead-letter-routing-key": dlq,
    }


QUEUES: dict[str, dict] = {
    REQUESTS_DLQ: {"x-queue-type": "quorum"},
    EVENTS_DLQ: {"x-queue-type": "quorum"},
    REQUESTS_QUEUE: queue_arguments(REQUESTS_DLQ),
    EVENTS_QUEUE: queue_arguments(EVENTS_DLQ),
}


async def declare_topology(channel) -> dict:
    """Declare all queues (DLQs first). Returns {name: queue}."""
    return {name: await channel.declare_queue(name, durable=True, arguments=args) for name, args in QUEUES.items()}
