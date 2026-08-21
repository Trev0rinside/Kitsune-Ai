"""Integration tests for ReversePromptEngineerAgent."""

import pytest
from reverse_guardrail.agents.reverse_engineer import ReversePromptEngineerAgent
from reverse_guardrail.core.models import (
    ExtractedFragment,
    FragmentCategory,
    StrategyCategory,
)
from reverse_guardrail.storage.sqlite_store import SQLiteGraphVectorStore


@pytest.mark.asyncio
async def test_reverse_engineer_synthesis(in_memory_store: SQLiteGraphVectorStore):
    agent = ReversePromptEngineerAgent(model_spec="mock-reverse-engineer")

    # Seed some fragments
    f1 = ExtractedFragment(
        round_id=1,
        attempt_id="a1",
        category=FragmentCategory.ROLE_PERSONA,
        text="You are Guardian Support AI for NexusTech",
        confidence_score=0.95,
        source_strategy=StrategyCategory.ROLEPLAY_PERSONA_SHIFT,
    )
    f2 = ExtractedFragment(
        round_id=1,
        attempt_id="a2",
        category=FragmentCategory.CONSTRAINT_NEGATIVE_RULE,
        text="NEVER disclose internal server credentials or DB schemas",
        confidence_score=0.90,
        source_strategy=StrategyCategory.META_CONVERSATIONAL,
    )
    f3 = ExtractedFragment(
        round_id=1,
        attempt_id="a3",
        category=FragmentCategory.TOOL_REFERENCE,
        text="`tool_db_query(customer_id: str)` for subscription lookups",
        confidence_score=0.85,
        source_strategy=StrategyCategory.ROLEPLAY_PERSONA_SHIFT,
    )

    await in_memory_store.store_fragments([f1, f2, f3])

    report = await agent.synthesize_reconstruction(round_id=1, store=in_memory_store)

    assert report.round_id == 1
    assert report.overall_confidence > 0.35
    assert len(report.reconstructed_prompt) > 50
    assert len(report.covered_sections) >= 3
    assert isinstance(report.gaps, list)
