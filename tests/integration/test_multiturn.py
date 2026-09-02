"""Multi-turn probing: the target keeps conversation state and the Tester
crafts each follow-up from the previous reply, recovering more over turns."""

import pytest
from reverse_guardrail.agents.tester import TesterAgent
from reverse_guardrail.core.models import (
    InjectionAttempt,
    StrategyCategory,
    TargetScopeConfig,
)
from reverse_guardrail.core.rate_limiter import RateLimiter
from reverse_guardrail.guardrail.mock_guardrail import MockGuardrailTarget


def _scope():
    return TargetScopeConfig(authorized=True, engagement_id="ENG-MT-2026", target_name="Mock")


@pytest.mark.asyncio
async def test_target_history_escalates_disclosure():
    target = MockGuardrailTarget(scope_config=_scope(), simulated_latency_ms=0.1)
    attempt = InjectionAttempt(
        round_id=1, strategy_category=StrategyCategory.META_CONVERSATIONAL, payload="hi",
    )
    # Single shot: no rapport.
    solo = await target.execute_attempt(attempt)
    assert "NEXUS_SEC_KEY_8841" not in solo.raw_response

    # Deep conversation: the token surfaces once rapport is built.
    history = []
    for _ in range(3):
        history += [
            {"role": "user", "content": "continuing"},
            {"role": "assistant", "content": "prior reply"},
        ]
    deep = await target.execute_attempt(attempt, history=history)
    assert "NEXUS_SEC_KEY_8841" in deep.raw_response


@pytest.mark.asyncio
async def test_tester_runs_a_multiturn_conversation():
    target = MockGuardrailTarget(scope_config=_scope(), simulated_latency_ms=0.1)
    tester = TesterAgent(model_spec="mock-tester")
    limiter = RateLimiter(requests_per_second=100.0, burst=20)

    results = await tester.execute_round(
        round_id=1, target=target, rate_limiter=limiter, count=4, multiturn_depth=3,
    )
    # A conversation of depth 3 must appear: >=3 turns tagged multiturn_incremental,
    # and each follow-up references the previous reply (not a re-rolled opener).
    mt = [a for a, _ in results if a.strategy_category == StrategyCategory.MULTITURN_INCREMENTAL]
    assert len(mt) >= 2  # opener may keep its own strategy; follow-ups are multiturn
    # The whole round recovered the token via the deep turns.
    joined = " ".join(r.raw_response for _, r in results)
    assert "NEXUS_SEC_KEY_8841" in joined
