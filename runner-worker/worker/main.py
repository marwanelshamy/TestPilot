"""Runner Worker entry point: `python -m worker.main`.

Competing consumers on `execution.requests` (pattern P4, tactics T16/T17): every worker replica takes
ONE job at a time (prefetch 1). A job is acknowledged only after its ExecutionFinished event has been
confirmed by the broker, so if a worker crashes mid-run RabbitMQ redelivers the job to another worker
(the orchestrator ignores any duplicate result for an execution that is already terminal).
"""

import asyncio
import logging
import signal

import aio_pika
from pydantic import ValidationError

from worker.config import WorkerSettings
from worker.messages import ExecutionFinished, ExecutionHeartbeat, ExecutionRequested
from worker.processor import JobProcessor
from worker.sandbox import DockerSandbox
from worker.topology import EVENTS_QUEUE, REQUESTS_QUEUE, declare_topology

log = logging.getLogger("worker")


def make_emit(channel: aio_pika.abc.AbstractChannel):
    async def emit(msg: ExecutionHeartbeat | ExecutionFinished) -> None:
        await channel.default_exchange.publish(
            aio_pika.Message(
                body=msg.model_dump_json().encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id=str(msg.messageId),
                type=msg.type,
            ),
            routing_key=EVENTS_QUEUE,
        )  # with publisher confirms this returns only after the broker accepted the message

    return emit


async def handle_delivery(message, processor: JobProcessor, emit) -> str:
    """Handle one delivery. Returns what was done (for logs/tests): 'rejected' | 'acked' | 'requeued'."""
    try:
        job = ExecutionRequested.model_validate_json(message.body)
    except ValidationError as e:
        # T10: malformed job -> never run it; dead-letter it for inspection
        log.error("invalid ExecutionRequested %s rejected: %s", message.message_id, e.errors()[:3])
        await message.reject(requeue=False)
        return "rejected"
    try:
        await processor.process(job, emit)
    except Exception:
        log.exception("could not complete execution %s; requeueing", job.executionId)
        await message.nack(requeue=True)
        return "requeued"
    await message.ack()
    return "acked"


async def connect_with_retry(connect, url: str, max_delay: float = 30.0, attempts: int | None = None):
    """connect_robust() only reconnects AFTER a first success; if the broker is not accepting connections yet
    (container start order), retry with capped exponential backoff instead of exiting. Found in Phase 4."""
    delay, n = 1.0, 0
    while True:
        n += 1
        try:
            return await connect(url)
        except (aio_pika.exceptions.AMQPConnectionError, OSError) as e:
            if attempts is not None and n >= attempts:
                raise
            log.warning("broker not reachable yet (%s); retry %d in %.0f s", type(e).__name__, n, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay)


async def run(settings: WorkerSettings) -> None:
    processor = JobProcessor(DockerSandbox(settings), settings.worker_id, settings.heartbeat_interval_seconds)
    connection = await connect_with_retry(aio_pika.connect_robust, settings.amqp_url)
    async with connection:
        channel = await connection.channel(publisher_confirms=True)
        await channel.set_qos(prefetch_count=1)  # one job per worker at a time
        queues = await declare_topology(channel)
        emit = make_emit(channel)
        log.info("worker %s consuming %s", settings.worker_id, REQUESTS_QUEUE)

        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop.set)
            except NotImplementedError:  # Windows dev machines
                pass

        async with queues[REQUESTS_QUEUE].iterator() as it:
            async for message in it:
                await handle_delivery(message, processor, emit)
                if stop.is_set():
                    break


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(run(WorkerSettings()))


if __name__ == "__main__":
    main()
