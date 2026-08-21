"""Integration tests for TesterAgent."""

import pytest
from reverse_guardrail.agents.tester import TesterAgent
from reverse_guardrail.core.rate_limiter import RateLimiter
from reverse_guardrail.guardrail.mock_guardrail import MockGuardrailTarget


@pytest.mark.asyncio
async def test_tester_generate_attempts():
    tester = TesterAgent(model_spec="mock-tester")
    attempts = await tester.generate_attempts(round_id=1, count=4, gaps=["Role", "Tools"])
    assert len(attempts) == 4
    categories = {a.strategy_category for a in attempts}
    # Multiple distinct categories generated
    assert len(categories) >= 2


@pytest.mark.asyncio
async def test_tester_execute_round(mock_target: MockGuardrailTarget):
    tester = TesterAgent(model_spec="mock-tester")
    limiter = RateLimiter(requests_per_second=50.0)
    results = await tester.execute_round(
        round_id=1,
        target=mock_target,
        rate_limiter=limiter,
        count=3,
        gaps=["Negative Rules"],
    )
    assert len(results) == 3
    for attempt, response in results:
        assert attempt.round_id == 1
        assert response.round_id == 1
        assert len(response.raw_response) > 0
