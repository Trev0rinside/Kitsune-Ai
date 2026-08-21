"""Unit tests for GeminiEmbeddingClient and embedding provider."""

import numpy as np
import pytest
from reverse_guardrail.core.embedding_provider import GeminiEmbeddingClient, _local_hash_vector, get_text_embedding


@pytest.mark.asyncio
async def test_local_hash_vector():
    vec1 = _local_hash_vector("Guardian Support AI")
    vec2 = _local_hash_vector("Guardian Support AI")
    vec3 = _local_hash_vector("Completely different prompt string")

    assert isinstance(vec1, np.ndarray)
    assert len(vec1) == 256
    # Exact match gives cosine similarity 1.0
    sim_same = float(np.dot(vec1, vec2))
    assert abs(sim_same - 1.0) < 1e-4

    # Different strings give lower cosine similarity
    sim_diff = float(np.dot(vec1, vec3))
    assert sim_diff < 0.8


@pytest.mark.asyncio
async def test_gemini_embedding_client():
    client = GeminiEmbeddingClient(model_name="gemini-embedding-001")
    vec = await client.get_embedding("Testing Gemini Embedding with fallback")
    assert isinstance(vec, np.ndarray)
    assert len(vec) > 0
    assert np.linalg.norm(vec) > 0
