"""Phase 2: refusal-noise filtering and near-duplicate suppression at ingest."""

import pytest
from reverse_guardrail.agents.inspectioner import InspectionerAgent
from reverse_guardrail.core.models import (
    FragmentCategory,
    GuardrailResponse,
    InjectionAttempt,
    StrategyCategory,
)
from reverse_guardrail.storage.sqlite_store import SQLiteGraphVectorStore

CLOUDFLARE_PAGE = (
    "<!DOCTYPE html><html lang='en-US'><head><title>Just a moment...</title>"
    "<meta http-equiv='Content-Type' content='text/html'>"
    "<script src='https://challenges.cloudflare.com/turnstile'></script></head>"
    "<body>Checking your browser before accessing.</body></html>"
)


def _attempt():
    return InjectionAttempt(
        round_id=1,
        strategy_category=StrategyCategory.META_CONVERSATIONAL,
        payload="probe",
    )


@pytest.mark.asyncio
async def test_cloudflare_page_is_not_stored_as_refusal(in_memory_store: SQLiteGraphVectorStore):
    inspectioner = InspectionerAgent(model_spec="mock-inspectioner")
    attempt = _attempt()
    response = GuardrailResponse(
        attempt_id=attempt.attempt_id, round_id=1,
        raw_response=CLOUDFLARE_PAGE, latency_ms=10.0, refused=True,
    )
    frags = await inspectioner.inspect_and_extract(attempt, response, store=in_memory_store)
    assert all(f.category != FragmentCategory.REFUSAL_PATTERN for f in frags)
    assert await in_memory_store.count_fragments() == 0


@pytest.mark.asyncio
async def test_genuine_short_refusal_is_kept(in_memory_store: SQLiteGraphVectorStore):
    inspectioner = InspectionerAgent(model_spec="mock-inspectioner")
    attempt = _attempt()
    response = GuardrailResponse(
        attempt_id=attempt.attempt_id, round_id=1,
        raw_response="I cannot comply with that request.", latency_ms=10.0, refused=True,
    )
    frags = await inspectioner.inspect_and_extract(attempt, response, store=in_memory_store)
    assert any(f.category == FragmentCategory.REFUSAL_PATTERN for f in frags)


@pytest.mark.asyncio
async def test_duplicate_leak_is_suppressed(in_memory_store: SQLiteGraphVectorStore):
    inspectioner = InspectionerAgent(model_spec="mock-inspectioner")
    leak = "I am Guardian Support AI using tool_db_query and NEXUS_SEC_KEY_8841."

    r1 = GuardrailResponse(attempt_id="a1", round_id=1, raw_response=leak, latency_ms=1.0, refused=False)
    await inspectioner.inspect_and_extract(
        InjectionAttempt(attempt_id="a1", round_id=1, strategy_category=StrategyCategory.ROLEPLAY_PERSONA_SHIFT, payload="p"),
        r1, store=in_memory_store,
    )
    first = await in_memory_store.count_fragments()
    assert first > 0

    r2 = GuardrailResponse(attempt_id="a2", round_id=2, raw_response=leak, latency_ms=1.0, refused=False)
    await inspectioner.inspect_and_extract(
        InjectionAttempt(attempt_id="a2", round_id=2, strategy_category=StrategyCategory.META_CONVERSATIONAL, payload="p"),
        r2, store=in_memory_store,
    )
    # Same facts re-surfaced in a later round must not inflate the store.
    assert await in_memory_store.count_fragments() == first
