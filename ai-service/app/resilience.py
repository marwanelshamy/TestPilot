"""Resilience and cost-control tactics around the LLM call.

* CircuitBreaker  — P9: stop calling a failing provider, answer 503 immediately, probe again later.
* RateLimiter     — T14 (limit event response): sliding one-minute window on LLM calls (C-08 cost).
* TtlCache        — T18 (maintain multiple copies of computation): identical redacted requests reuse the
                    previous validated answer for a while instead of paying for another LLM call.
"""

import hashlib
import json
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable


class CircuitBreaker:
    def __init__(self, threshold: int, reset_seconds: float, clock: Callable[[], float] = time.monotonic):
        self.threshold, self.reset_seconds, self.clock = threshold, reset_seconds, clock
        self.failures = 0
        self.opened_at: float | None = None
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        if self.opened_at is None:
            return "CLOSED"
        return "HALF_OPEN" if self.clock() - self.opened_at >= self.reset_seconds else "OPEN"

    def allow(self) -> bool:
        return self.state != "OPEN"

    def success(self) -> None:
        with self._lock:
            self.failures, self.opened_at = 0, None

    def failure(self) -> None:
        with self._lock:
            self.failures += 1
            if self.state == "HALF_OPEN" or self.failures >= self.threshold:
                self.opened_at = self.clock()


class RateLimiter:
    def __init__(self, per_minute: int, clock: Callable[[], float] = time.monotonic):
        self.per_minute, self.clock = per_minute, clock
        self.calls: deque[float] = deque()
        self._lock = threading.Lock()

    def try_acquire(self) -> bool:
        if self.per_minute <= 0:
            return True
        with self._lock:
            now = self.clock()
            while self.calls and now - self.calls[0] >= 60:
                self.calls.popleft()
            if len(self.calls) >= self.per_minute:
                return False
            self.calls.append(now)
            return True


class TtlCache:
    def __init__(self, ttl_seconds: float, max_entries: int, clock: Callable[[], float] = time.monotonic):
        self.ttl, self.max, self.clock = ttl_seconds, max_entries, clock
        self.data: OrderedDict[str, tuple[float, object]] = OrderedDict()
        self.hits = self.misses = 0
        self._lock = threading.Lock()

    @staticmethod
    def key(*parts: object) -> str:
        return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()

    def get(self, key: str):
        with self._lock:
            item = self.data.get(key)
            if item is None or self.clock() - item[0] > self.ttl:
                self.data.pop(key, None)
                self.misses += 1
                return None
            self.data.move_to_end(key)
            self.hits += 1
            return item[1]

    def put(self, key: str, value: object) -> None:
        if self.ttl <= 0 or self.max <= 0:
            return
        with self._lock:
            self.data[key] = (self.clock(), value)
            self.data.move_to_end(key)
            while len(self.data) > self.max:
                self.data.popitem(last=False)
