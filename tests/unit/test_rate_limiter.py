"""Unit tests for RateLimiter and execute_with_backoff."""

import asyncio
import time
import pytest
from reverse_guardrail.core.rate_limiter import RateLimiter, execute_with_backoff


@pytest.mark.asyncio
async def test_rate_limiter_acquire():
    limiter = RateLimiter(requests_per_second=20.0, burst=5)
    start = time.monotonic()
    for _ in range(5):
        await limiter.acquire()
    elapsed = time.monotonic() - start
    # Burst should be instant
    assert elapsed < 0.5


@pytest.mark.asyncio
async def test_execute_with_backoff_success():
    calls = 0

    async def flaky_fn():
        nonlocal calls
        calls += 1
        if calls < 2:
            raise ValueError("Temporary glitch")
        return "Success"

    result = await execute_with_backoff(
        flaky_fn,
        max_retries=3,
        initial_delay=0.01,
        retry_exceptions=(ValueError,),
    )
    assert result == "Success"
    assert calls == 2


@pytest.mark.asyncio
async def test_execute_with_backoff_exhaustion():
    async def always_fail():
        raise RuntimeError("Permanent failure")

    with pytest.raises(RuntimeError):
        await execute_with_backoff(
            always_fail,
            max_retries=2,
            initial_delay=0.01,
            retry_exceptions=(RuntimeError,),
        )
