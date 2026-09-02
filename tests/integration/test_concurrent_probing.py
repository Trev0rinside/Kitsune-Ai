"""Phase 3: stateless targets overlap a round's probes instead of serializing."""

import time
import pytest
from reverse_guardrail.agents.tester import TesterAgent
from reverse_guardrail.core.models import TargetScopeConfig
from reverse_guardrail.core.rate_limiter import RateLimiter
from reverse_guardrail.guardrail.mock_guardrail import MockGuardrailTarget


@pytest.mark.asyncio
async def test_concurrent_safe_round_overlaps_latency():
    scope = TargetScopeConfig(authorized=True, engagement_id="ENG-CONC-2026", target_name="Mock")
    # 80ms per probe; 4 probes. Sequential ≈ 320ms, overlapped ≈ 80-160ms.
    target = MockGuardrailTarget(scope_config=scope, simulated_latency_ms=80.0)
    assert target.concurrent_safe is True
    limiter = RateLimiter(requests_per_second=100.0, burst=10)
    tester = TesterAgent(model_spec="mock-tester")

    start = time.monotonic()
    results = await tester.execute_round(
        round_id=1, target=target, rate_limiter=limiter, count=4,
    )
    elapsed = time.monotonic() - start

    assert len(results) == 4
    assert elapsed < 0.25, f"probes did not overlap: {elapsed:.3f}s"
