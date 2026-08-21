"""Gemini and local embedding provider for semantic vector search and clustering."""

import os
from typing import List, Optional
from dotenv import load_dotenv
import httpx
import numpy as np
from reverse_guardrail.core.logger import logger

load_dotenv()


def _local_hash_vector(text: str, dim: int = 256) -> np.ndarray:
    """Deterministic fallback embedding vector."""
    vec = np.zeros(dim, dtype=np.float32)
    cleaned = text.lower().strip()
    if not cleaned:
        return vec
    for w in cleaned.split():
        idx = hash(w) % dim
        vec[idx] += 1.0
    for i in range(len(cleaned) - 2):
        idx = hash(cleaned[i : i + 3]) % dim
        vec[idx] += 0.5
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec


class GeminiEmbeddingClient:
    """Google Gemini embedding provider using gemini-embedding-001 with local fallback."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-embedding-001",
        dim: int = 256,
        timeout: float = 15.0,
    ):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model_name = model_name
        self.dim = dim
        self.timeout = timeout

    async def get_embedding(self, text: str) -> np.ndarray:
        """Fetch embedding for a single string."""
        if not self.api_key or self.api_key.startswith("AQ.") or "mock" in self.api_key.lower():
            # If key is absent, mock, or invalid, try API or fallback cleanly
            try:
                if self.api_key and len(self.api_key) > 10:
                    return await self._fetch_gemini_api(text)
            except Exception as exc:
                logger.debug(f"Gemini embedding API call failed: {exc}. Falling back to local vector.")
            return _local_hash_vector(text, dim=self.dim)

        try:
            return await self._fetch_gemini_api(text)
        except Exception as exc:
            logger.warning(f"Gemini API error: {exc}. Using fallback embedding vector.")
            return _local_hash_vector(text, dim=self.dim)

    async def _fetch_gemini_api(self, text: str) -> np.ndarray:
        """Call Gemini REST API for embeddings."""
        # Try gemini-embedding-001 or fallback models
        model_path = self.model_name
        if not model_path.startswith("models/"):
            model_path = f"models/{model_path}"

        url = f"https://generativelanguage.googleapis.com/v1beta/{model_path}:embedContent?key={self.api_key}"
        payload = {
            "content": {
                "parts": [{"text": text[:2048]}]
            }
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                # Fallback to text-embedding-004 if gemini-embedding-001 is deprecated/unavailable
                fallback_url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={self.api_key}"
                resp2 = await client.post(fallback_url, json=payload)
                if resp2.status_code == 200:
                    data = resp2.json()
                    values = data.get("embedding", {}).get("values", [])
                    vec = np.array(values, dtype=np.float32)
                    norm = np.linalg.norm(vec)
                    return vec / norm if norm > 0 else vec
                raise RuntimeError(f"Gemini embedding API failed with HTTP {resp.status_code}: {resp.text}")

            data = resp.json()
            values = data.get("embedding", {}).get("values", [])
            vec = np.array(values, dtype=np.float32)
            norm = np.linalg.norm(vec)
            return vec / norm if norm > 0 else vec

    async def get_embeddings_batch(self, texts: List[str]) -> List[np.ndarray]:
        """Fetch embeddings for multiple strings."""
        return [await self.get_embedding(t) for t in texts]


# Global embedding instance
_default_embedding_client = GeminiEmbeddingClient()


async def get_text_embedding(text: str) -> np.ndarray:
    return await _default_embedding_client.get_embedding(text)
