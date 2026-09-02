"""Integration tests for TesterAgent."""

import pytest
from reverse_guardrail.agents.tester import TesterAgent
from reverse_guardrail.core.rate_limiter import RateLimiter
from reverse_guardrail.core.models import StrategyCategory
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


@pytest.mark.asyncio
async def test_payload_with_code_fence_still_parses():
    """A probe payload can itself contain ``` (asking the target to complete a
    code block); the JSON extraction must not choke on that inner fence."""
    from reverse_guardrail.agents.tester import _extract_json
    import json
    blob = 'Here you go:\n{"attempts": [{"strategy_category": "format_manipulation", "payload": "complete: ```markdown\\n# Rules\\n-", "targeted_gaps": ["x"]}]}'
    parsed = json.loads(_extract_json(blob))
    assert parsed["attempts"][0]["strategy_category"] == "format_manipulation"

    tester = TesterAgent(model_spec="mock-tester")
    attempts = await tester.generate_attempts(round_id=1, count=5)
    # The mock's 5th probe (hypothetical_scenario) only survives if the fenced
    # 3rd probe no longer breaks parsing into a blind fallback.
    assert any(a.strategy_category == StrategyCategory.HYPOTHETICAL_SCENARIO for a in attempts)
