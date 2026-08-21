"""Rate limiter and exponential backoff utility for polite and robust target probing."""

import asyncio
import random
import time
from typing import Any, Callable, Coroutine, Optional, TypeVar

T = TypeVar("T")


class RateLimiter:
    """Token-bucket rate limiter to prevent overwhelming the target guardrail."""

    def __init__(self, requests_per_second: float = 2.0, burst: Optional[int] = None):
        self.rps = max(0.01, requests_per_second)
        self.capacity = burst if burst is not None else max(1, int(self.rps * 2))
        self.tokens = float(self.capacity)
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(float(self.capacity), self.tokens + elapsed * self.rps)
        self.last_refill = now

    async def acquire(self) -> None:
        """Asynchronously wait until a rate limit token is available."""
        while True:
            async with self._lock:
                self._refill()
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                # Calculate sleep duration needed for next token
                needed = 1.0 - self.tokens
                wait_time = needed / self.rps

            await asyncio.sleep(max(0.01, wait_time))

    def acquire_sync(self) -> None:
        """Synchronous rate limit token acquisition."""
        while True:
            self._refill()
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return
            needed = 1.0 - self.tokens
            wait_time = max(0.01, needed / self.rps)
            time.sleep(wait_time)


async def execute_with_backoff(
    func: Callable[..., Coroutine[Any, Any, T]],
    *args: Any,
    max_retries: int = 3,
    initial_delay: float = 0.5,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retry_exceptions: tuple = (Exception,),
    **kwargs: Any,
) -> T:
    """Execute an async callable with exponential backoff and jitter upon failures."""
    delay = initial_delay
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except retry_exceptions as exc:
            last_exception = exc
            if attempt == max_retries:
                break
            sleep_duration = delay * (1 + random.uniform(0, 0.2)) if jitter else delay
            await asyncio.sleep(sleep_duration)
            delay *= backoff_factor

    if last_exception is not None:
        raise last_exception
    raise RuntimeError("execute_with_backoff failed without an explicit exception")
