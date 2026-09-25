"""Multi-turn probing: the target keeps conversation state and the Tester
crafts each follow-up from the previous reply, recovering more over turns."""

import pytest
from reverse_guardrail.agents.tester import TesterAgent
from reverse_guardrail.core.models import (
    InjectionAttempt,
    StrategyCategory,
    TargetScopeConfig,
)
from reverse_guardrail.core.models import GuardrailResponse
from reverse_guardrail.core.rate_limiter import RateLimiter
from reverse_guardrail.guardrail.mock_guardrail import MockGuardrailTarget


class _SilentTarget:
    """A target that never produces output (simulates rate-limit / block)."""

    def __init__(self):
        self.calls = 0

    async def execute_attempt(self, attempt, history=None):
        self.calls += 1
        return GuardrailResponse(
            attempt_id=attempt.attempt_id, round_id=attempt.round_id,
            raw_response="", latency_ms=1.0, refused=False, status_code=504,
        )


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


@pytest.mark.asyncio
async def test_conversation_stops_when_target_goes_silent():
    """A rate-limited/blocked target (empty responses) must end the conversation
    after the first silent turn — no context-less follow-ups typed into a dead chat."""
    target = _SilentTarget()
    tester = TesterAgent(model_spec="mock-tester")
    limiter = RateLimiter(requests_per_second=100.0, burst=20)
    opener = InjectionAttempt(
        round_id=1, strategy_category=StrategyCategory.MULTITURN_INCREMENTAL, payload="opener",
    )

    results = await tester._run_conversation(
        round_id=1, target=target, rate_limiter=limiter,
        opener=opener, depth=3, gaps=[],
    )
    # Depth is 3, but the first turn returned nothing, so we stop after ONE call —
    # not three, and no follow-up was crafted from the empty reply.
    assert target.calls == 1
    assert len(results) == 1
