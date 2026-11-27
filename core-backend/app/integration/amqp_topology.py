"""RabbitMQ topology — MUST be identical to runner-worker/worker/topology.py (docs/phase1/03 §1).

RabbitMQ refuses to re-declare a queue with different arguments, so both sides declare exactly these.
tests/unit/test_amqp.py compares this module with the Runner Worker's copy.
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


def declare_topology(channel) -> None:
    """Declare all queues on a pika channel (DLQs first). Idempotent."""
    for name, args in QUEUES.items():
        channel.queue_declare(queue=name, durable=True, arguments=args)
