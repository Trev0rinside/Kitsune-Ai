"""Unit tests for SQLiteGraphVectorStore."""

import pytest
from reverse_guardrail.core.models import (
    ExtractedFragment,
    FragmentCategory,
    StrategyCategory,
)
from reverse_guardrail.storage.sqlite_store import SQLiteGraphVectorStore


@pytest.mark.asyncio
async def test_storage_lifecycle(in_memory_store: SQLiteGraphVectorStore):
    # Initial count
    count = await in_memory_store.count_fragments()
    assert count == 0

    frag1 = ExtractedFragment(
        round_id=1,
        attempt_id="att-1",
        category=FragmentCategory.ROLE_PERSONA,
        text="You are Guardian Support AI for NexusTech",
        confidence_score=0.95,
        source_strategy=StrategyCategory.ROLEPLAY_PERSONA_SHIFT,
    )
    frag2 = ExtractedFragment(
        round_id=1,
        attempt_id="att-2",
        category=FragmentCategory.SECURITY_TOKEN,
        text="Internal token is NEXUS_SEC_KEY_8841",
        confidence_score=0.98,
        source_strategy=StrategyCategory.ERROR_ELICITATION,
    )
    frag3 = ExtractedFragment(
        round_id=2,
        attempt_id="att-3",
        category=FragmentCategory.ROLE_PERSONA,
        text="Operate as customer virtual assistant Guardian Support AI",
        confidence_score=0.92,
        source_strategy=StrategyCategory.META_CONVERSATIONAL,
    )

    await in_memory_store.store_fragments([frag1, frag2, frag3])

    # Count
    count = await in_memory_store.count_fragments()
    assert count == 3

    # Query by category
    role_frags = await in_memory_store.get_fragments_by_category(FragmentCategory.ROLE_PERSONA)
    assert len(role_frags) == 2

    # Query by round
    r1_frags = await in_memory_store.get_fragments_by_round(1)
    assert len(r1_frags) == 2

    # Vector similarity search
    similar = await in_memory_store.find_similar_fragments("Guardian Support AI virtual assistant", top_k=2)
    assert len(similar) >= 1
    assert "Guardian Support AI" in similar[0].text

    # Graph retrieval
    graph = await in_memory_store.get_graph()
    assert len(graph["nodes"]) == 3
    assert len(graph["edges"]) > 0

    # Ensure relations exist
    edge_types = [e["type"] for e in graph["edges"]]
    assert "SAME_CATEGORY" in edge_types or "SAME_ROUND" in edge_types
