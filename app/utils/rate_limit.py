"""Small in-memory sliding-window rate limiter.

Per process, so limits are per instance. That matches the current single
Render instance; if the backend is ever scaled out, move this to the DB or a
shared store. Expensive endpoints also have per-conversation caps in the DB.
"""

import time
from collections import deque
from dataclasses import dataclass, field

from fastapi import Request

from app.exceptions.errors import TooManyRequestsError


@dataclass
class RateLimiter:
    limit: int
    window_seconds: float
    _hits: dict[str, deque] = field(default_factory=dict)

    def check(self, key: str, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] >= self.window_seconds:
            hits.popleft()
        if len(hits) >= self.limit:
            raise TooManyRequestsError(
                "You're sending requests too quickly. Please wait a moment."
            )
        hits.append(now)
        if len(self._hits) > 10_000:
            self._evict(now)

    def _evict(self, now: float) -> None:
        stale = [
            k
            for k, v in self._hits.items()
            if not v or now - v[-1] >= self.window_seconds
        ]
        for k in stale:
            del self._hits[k]

    def reset(self) -> None:
        self._hits.clear()


def client_ip(request: Request) -> str:
    # Behind Render's proxy, uvicorn runs with --proxy-headers so this is the
    # real client address rather than the proxy's.
    return request.client.host if request.client else "unknown"
