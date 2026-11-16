"""Small in-memory rate limiter.

Good for a single backend instance (free hosting tier). With several instances,
move the counters to Redis.
"""
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


class RateLimiter:
    def __init__(self):
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - window_seconds:
                q.popleft()
            if len(q) >= limit:
                retry = int(window_seconds - (now - q[0])) + 1
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    "Too many requests. Please wait and try again.",
                    headers={"Retry-After": str(retry)},
                )
            q.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    """The visitor's real IP address, used for rate limits and the audit log.

    X-Forwarded-For can be typed by anyone, so only the entries added by our own
    hosting proxies are trusted: with TRUSTED_PROXY_HOPS=1 (one proxy, e.g. Render)
    we take the LAST entry, which that proxy wrote. With 0 the header is ignored.
    """
    from app.config import get_settings

    hops = get_settings().trusted_proxy_hops
    fwd = request.headers.get("x-forwarded-for")
    if hops > 0 and fwd:
        parts = [p.strip() for p in fwd.split(",") if p.strip()]
        if parts:
            return parts[-hops] if len(parts) >= hops else parts[0]
    return request.client.host if request.client else "unknown"


def rate_limit(name: str, limit: int, window_seconds: int = 60):
    """FastAPI dependency: `Depends(rate_limit("checkout", 20))`."""

    def _dep(request: Request) -> None:
        limiter.check(f"{name}:{client_ip(request)}", limit, window_seconds)

    return _dep
