"""In-memory sliding-window rate limits (API 7). One process (D17), so a dict is enough;
counters reset on restart (accepted, ARCHITECTURE 14.3)."""

import math
import threading
import time
from collections import deque
from collections.abc import Callable

from app.services.errors import AppError


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _window(self, key: str, period: float) -> deque[float]:
        q = self._hits.setdefault(key, deque())
        cutoff = self.clock() - period
        while q and q[0] <= cutoff:
            q.popleft()
        return q

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
            self._hits.setdefault(key, deque()).append(self.clock())

    def clear(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def check(self, key: str, limit: int, period: float) -> None:
        wait = self.retry_after(key, limit, period)
        if wait:
            raise AppError("rate_limited", headers={"Retry-After": str(wait)}, n=wait)
