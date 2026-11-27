"""Admission control — bound the number of requests in flight (Phase 5, QAS-1 finding).

Why: FastAPI runs sync endpoints on a worker-thread pool (40 threads), and every endpoint holds a pooled DB
connection until its response has been serialised — which needs a worker thread again. With 200 concurrent
users all 40 threads ended up blocked waiting for a DB connection while every connection was held by a finished
request waiting for a thread: a convoy deadlock (evidence: evidence/qas1_retrieval/results/run2-pyspy-thread-dump.txt).

Tactic: admit at most `max_inflight` requests at once (fewer than both the thread pool and the connection
pool), so a finishing request always finds a free thread and returns its connection. Excess requests wait in a
FIFO queue on the event loop (no thread, no connection); after `wait_seconds` they get 503 SERVICE_BUSY.
`/api/health` is never queued, so liveness checks keep working under overload.
"""

import asyncio
import json
import uuid

from starlette.types import ASGIApp, Receive, Scope, Send

EXEMPT = {"/api/health"}


class AdmissionControl:
    def __init__(self, app: ASGIApp, max_inflight: int, wait_seconds: float):
        self.app = app
        self.max_inflight = max_inflight
        self.wait_seconds = wait_seconds
        self._sem: asyncio.Semaphore | None = None  # created lazily on the server's event loop
        self.rejected = 0

    @property
    def sem(self) -> asyncio.Semaphore:
        if self._sem is None:
            self._sem = asyncio.Semaphore(self.max_inflight)
        return self._sem

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in EXEMPT or self.max_inflight <= 0:
            await self.app(scope, receive, send)
            return
        try:
            await asyncio.wait_for(self.sem.acquire(), timeout=self.wait_seconds)
        except TimeoutError:
            self.rejected += 1
            await self._busy(scope, send)
            return
        try:
            await self.app(scope, receive, send)
        finally:
            self.sem.release()

    @staticmethod
    async def _busy(scope: Scope, send: Send) -> None:
        headers = dict(scope.get("headers") or [])
        cid = headers.get(b"x-correlation-id", uuid.uuid4().hex[:12].encode()).decode()
        body = json.dumps(
            {
                "error": {
                    "code": "SERVICE_BUSY",
                    "message": "The service is busy. Please retry in a moment.",
                    "details": {},
                    "correlationId": cid,
                }
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 503,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"retry-after", b"1"),
                    (b"x-correlation-id", cid.encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
