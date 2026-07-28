"""
Minimal in-memory sliding-window rate limiter, keyed by client IP.
Good enough for a demo/portfolio project running a single process.
For production/multi-instance deployments swap this for Redis
(the interface is deliberately small so that's a drop-in change).
"""
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        q = self._hits[key]
        while q and now - q[0] > self.window_seconds:
            q.popleft()
        if len(q) >= self.max_requests:
            return False
        q.append(now)
        return True

    def retry_after(self, key: str) -> float:
        q = self._hits[key]
        if not q:
            return 0.0
        return max(0.0, self.window_seconds - (time.monotonic() - q[0]))
