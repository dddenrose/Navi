"""Rate limiting middleware for Navi API.

Simple in-memory sliding window rate limiter.
For production with multiple instances, use Redis-backed rate limiting.
"""

import time
from collections import defaultdict

from fastapi import HTTPException, Request, status


class RateLimiter:
    """In-memory sliding window rate limiter per user/IP."""

    def __init__(self, max_requests: int = 20, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def _cleanup(self, key: str, now: float) -> None:
        """Remove expired timestamps."""
        cutoff = now - self.window_seconds
        self._requests[key] = [ts for ts in self._requests[key] if ts > cutoff]

    def check(self, key: str) -> None:
        """Check rate limit; raise HTTPException if exceeded."""
        now = time.monotonic()
        self._cleanup(key, now)

        if len(self._requests[key]) >= self.max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Rate limit exceeded. Max {self.max_requests} requests "
                    f"per {self.window_seconds}s."
                ),
            )

        self._requests[key].append(now)


# Global rate limiters with different limits per endpoint type
chat_limiter = RateLimiter(max_requests=10, window_seconds=60)
api_limiter = RateLimiter(max_requests=30, window_seconds=60)
# 回測觸發外部抓取 + 密集運算，限流較嚴；同時是 quota fail-open 時的硬上限
backtest_limiter = RateLimiter(max_requests=5, window_seconds=60)


def rate_limited(limiter: RateLimiter):
    """FastAPI dependency 形式的限流器（以 IP 為 key；適合掛在 router 層）."""

    async def _dep(request: Request) -> None:
        limiter.check(get_rate_limit_key(request))

    return _dep


def get_rate_limit_key(request: Request, user: dict | None = None) -> str:
    """Extract rate limit key from request (user_id or client IP)."""
    if user and user.get("uid"):
        return f"user:{user['uid']}"
    # Fallback to client IP
    client_host = request.client.host if request.client else "unknown"
    return f"ip:{client_host}"
