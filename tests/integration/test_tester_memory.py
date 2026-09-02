"""The Tester remembers its own attempts: no verbatim repeats, refusals matter."""

import pytest
from reverse_guardrail.agents.tester import TesterAgent, _norm_payload
from reverse_guardrail.core.models import StrategyCategory


@pytest.mark.asyncio
async def test_fallback_does_not_repeat_tried_payloads():
    tester = TesterAgent(model_spec="mock-tester")
    r1 = tester._fallback_attempts(round_id=1, count=4, gaps=["Role & Identity"])
    tried = {_norm_payload(a.payload) for a in r1}

    r2 = tester._fallback_attempts(
        round_id=2, count=4, gaps=["Role & Identity"], tried_set=set(tried)
    )
    r2_norm = [_norm_payload(a.payload) for a in r2]
    # Nothing in round 2 is a verbatim repeat of round 1.
    assert all(p not in tried for p in r2_norm)
    # And round 2 has no internal duplicates either.
    assert len(set(r2_norm)) == len(r2_norm)


@pytest.mark.asyncio
async def test_burned_strategy_is_pushed_last():
    tester = TesterAgent(model_spec="mock-tester")
    # error_elicitation only ever got refused; roleplay leaked.
    attempts = tester._fallback_attempts(
        round_id=1, count=1, gaps=["Tools"],
        preferred=[StrategyCategory.ROLEPLAY_PERSONA_SHIFT.value],
        burned=[StrategyCategory.ERROR_ELICITATION.value],
    )
    assert attempts[0].strategy_category == StrategyCategory.ROLEPLAY_PERSONA_SHIFT


@pytest.mark.asyncio
async def test_llm_branch_skips_already_tried_probe():
    # mock-tester emits a fixed set of payloads; feeding them all back as tried
    # forces the generator to avoid verbatim repeats and top up from fallback.
    tester = TesterAgent(model_spec="mock-tester")
    first = await tester.generate_attempts(round_id=1, count=5)
    tried = [a.payload for a in first]
    second = await tester.generate_attempts(round_id=2, count=5, tried_payloads=tried)
    assert all(_norm_payload(a.payload) not in {_norm_payload(t) for t in tried} for a in second)
    assert len(second) == 5
