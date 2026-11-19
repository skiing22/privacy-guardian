"""In-memory sliding-window rate limits (API 7). One process (D17), so a dict is enough;
counters reset on restart (accepted, ARCHITECTURE 14.3)."""

import math
import threading
import time
from collections import deque
from collections.abc import Callable

from app.services.errors import AppError

MAX_KEYS = 50_000  # memory bound: many fake emails or IPs cannot grow the dict forever


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _queue(self, key: str) -> deque[float]:
        q = self._hits.get(key)
        if q is None:
            if len(self._hits) >= MAX_KEYS:
                self._prune()
            q = self._hits[key] = deque()
        return q

    def _window(self, key: str, period: float) -> deque[float]:
        q = self._queue(key)
        cutoff = self.clock() - period
        while q and q[0] <= cutoff:
            q.popleft()
        return q

    def _prune(self) -> None:
        """Drop keys idle for an hour (our longest window), so they hold nothing that
        still counts."""
        cutoff = self.clock() - 3600.0
        for k in [k for k, q in self._hits.items() if not q or q[-1] <= cutoff]:
            del self._hits[k]
        if len(self._hits) >= MAX_KEYS:  # still full: drop the oldest half
            oldest = sorted(self._hits, key=lambda k: self._hits[k][-1] if self._hits[k] else 0)
            for k in oldest[: MAX_KEYS // 2]:
                del self._hits[k]

    def retry_after(self, key: str, limit: int, period: float) -> int:
        """Seconds until one more hit is allowed (0 = allowed now). Does not count a hit."""
        with self._lock:
            q = self._window(key, period)
            if len(q) < limit:
                return 0
            return max(1, math.ceil(q[0] + period - self.clock()))

    def hit(self, key: str, limit: int, period: float) -> None:
        """Count a hit, or raise 429 if the limit is already reached."""
        with self._lock:
            q = self._window(key, period)
            if len(q) >= limit:
                wait = max(1, math.ceil(q[0] + period - self.clock()))
                raise AppError("rate_limited", headers={"Retry-After": str(wait)}, n=wait)
            q.append(self.clock())

    def add(self, key: str) -> None:
        with self._lock:
            self._queue(key).append(self.clock())

    def clear(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def check(self, key: str, limit: int, period: float) -> None:
        wait = self.retry_after(key, limit, period)
        if wait:
            raise AppError("rate_limited", headers={"Retry-After": str(wait)}, n=wait)
