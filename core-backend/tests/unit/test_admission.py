"""Admission control (Phase 5, QAS-1 finding): at most N requests in flight, FIFO wait on the event loop,
503 SERVICE_BUSY after the wait limit, health never queued."""

import asyncio

import httpx
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.api.admission import AdmissionControl


async def slow(request):
    await asyncio.sleep(0.3)
    return JSONResponse({"ok": True})


async def health(request):
    return JSONResponse({"status": "ok"})


def make(max_inflight=1, wait=0.05):
    inner = Starlette(routes=[Route("/api/slow", slow), Route("/api/health", health)])
    return AdmissionControl(inner, max_inflight=max_inflight, wait_seconds=wait)


def run(coro):
    return asyncio.run(coro)


async def burst(app, n, path="/api/slow"):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        return await asyncio.gather(*[c.get(path) for _ in range(n)])


def test_excess_requests_get_a_clean_503():
    app = make(max_inflight=2, wait=0.05)
    codes = sorted(r.status_code for r in run(burst(app, 5)))
    assert codes == [200, 200, 503, 503, 503]
    busy = next(r for r in run(burst(make(1, 0.01), 2)) if r.status_code == 503)
    assert busy.json()["error"]["code"] == "SERVICE_BUSY" and busy.headers["retry-after"] == "1"


def test_waiting_requests_are_served_when_a_slot_frees():
    app = make(max_inflight=1, wait=2.0)  # long enough to wait for the first one
    assert [r.status_code for r in run(burst(app, 3))] == [200, 200, 200]


def test_health_is_never_queued():
    app = make(max_inflight=1, wait=0.01)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            busy = asyncio.create_task(c.get("/api/slow"))
            await asyncio.sleep(0.05)
            h = await c.get("/api/health")
            await busy
            return h

    assert run(scenario()).status_code == 200


def test_backend_has_admission_control_installed(app):
    assert any(m.cls is AdmissionControl for m in app.user_middleware)
