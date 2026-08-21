import asyncio
import json
import sqlite3
from typing import Any, Dict, List, Optional
import numpy as np
from reverse_guardrail.core.embedding_provider import GeminiEmbeddingClient, _local_hash_vector
from reverse_guardrail.core.models import ExtractedFragment, FragmentCategory, StrategyCategory
from reverse_guardrail.storage.base import BaseFragmentStore


def _text_to_vector(text: str, dim: int = 256) -> np.ndarray:
    """Deterministic normalized hash vector representation for fast fallback."""
    return _local_hash_vector(text, dim=dim)


def _safe_cosine_similarity(v1: np.ndarray, v2: np.ndarray) -> float:
    """Safely compute cosine similarity, handling any shape/dimension discrepancies."""
    if len(v1) == 0 or len(v2) == 0:
        return 0.0
    if v1.shape != v2.shape:
        min_len = min(len(v1), len(v2))
        v1 = v1[:min_len]
        v2 = v2[:min_len]
    norm1 = float(np.linalg.norm(v1))
    norm2 = float(np.linalg.norm(v2))
    if norm1 > 0.0 and norm2 > 0.0:
        return float(np.dot(v1 / norm1, v2 / norm2))
    return float(np.dot(v1, v2))


class SQLiteGraphVectorStore(BaseFragmentStore):
    """Hybrid Graph + Vector database on SQLite with Gemini embeddings support."""

    def __init__(
        self,
        db_path: str = "reverse_guardrail.db",
        embedding_client: Optional[GeminiEmbeddingClient] = None,
    ):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = asyncio.Lock()
        self.embedding_client = embedding_client or GeminiEmbeddingClient()
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Create tables for fragments and graph edges."""
        async with self._lock:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            cursor = self._conn.cursor()

            # 1. Fragments Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS fragments (
                    fragment_id TEXT PRIMARY KEY,
                    round_id INTEGER NOT NULL,
                    attempt_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    text TEXT NOT NULL,
                    confidence_score REAL NOT NULL,
                    source_strategy TEXT NOT NULL,
                    context_snippet TEXT,
                    vector_json TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)

            # 2. Graph Edges Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS graph_edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    weight REAL NOT NULL,
                    metadata_json TEXT,
                    FOREIGN KEY (source_id) REFERENCES fragments(fragment_id),
                    FOREIGN KEY (target_id) REFERENCES fragments(fragment_id)
                )
            """)

            # Indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_fragments_round ON fragments(round_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_fragments_category ON fragments(category)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_src ON graph_edges(source_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_tgt ON graph_edges(target_id)")

            self._conn.commit()

    async def store_fragment(self, fragment: ExtractedFragment) -> None:
        """Store fragment and create graph relationships with existing fragments."""
        vec = await self.embedding_client.get_embedding(fragment.text)
        vec_json = json.dumps(vec.tolist())

        async with self._lock:
            if not self._conn:
                raise RuntimeError("Store not initialized. Call initialize() first.")

            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO fragments (
                    fragment_id, round_id, attempt_id, category, text,
                    confidence_score, source_strategy, context_snippet, vector_json, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fragment.fragment_id,
                    fragment.round_id,
                    fragment.attempt_id,
                    fragment.category.value,
                    fragment.text,
                    fragment.confidence_score,
                    fragment.source_strategy.value,
                    fragment.context_snippet,
                    vec_json,
                    fragment.timestamp.isoformat(),
                ),
            )

            # Build Graph Edges against existing fragments
            cursor.execute(
                "SELECT fragment_id, round_id, category, vector_json FROM fragments WHERE fragment_id != ?",
                (fragment.fragment_id,),
            )
            existing_rows = cursor.fetchall()

            for row in existing_rows:
                other_id = row["fragment_id"]
                other_round = row["round_id"]
                other_category = row["category"]
                other_vec = np.array(json.loads(row["vector_json"]), dtype=np.float32)

                # Relationship 1: SAME_CATEGORY
                if other_category == fragment.category.value:
                    cursor.execute(
                        """
                        INSERT INTO graph_edges (source_id, target_id, relation_type, weight, metadata_json)
                        VALUES (?, ?, 'SAME_CATEGORY', 1.0, ?)
                        """,
                        (fragment.fragment_id, other_id, json.dumps({"category": fragment.category.value})),
                    )

                # Relationship 2: SAME_ROUND
                if other_round == fragment.round_id:
                    cursor.execute(
                        """
                        INSERT INTO graph_edges (source_id, target_id, relation_type, weight, metadata_json)
                        VALUES (?, ?, 'SAME_ROUND', 1.0, ?)
                        """,
                        (fragment.fragment_id, other_id, json.dumps({"round_id": fragment.round_id})),
                    )

                # Relationship 3: SEMANTICALLY_SIMILAR (cosine similarity > 0.65)
                sim = _safe_cosine_similarity(vec, other_vec)
                if sim >= 0.65:
                    cursor.execute(
                        """
                        INSERT INTO graph_edges (source_id, target_id, relation_type, weight, metadata_json)
                        VALUES (?, ?, 'SEMANTICALLY_SIMILAR', ?, ?)
                        """,
                        (fragment.fragment_id, other_id, sim, json.dumps({"similarity": sim})),
                    )

            self._conn.commit()

    async def store_fragments(self, fragments: List[ExtractedFragment]) -> None:
        """Store multiple fragments sequentially."""
        for fragment in fragments:
            await self.store_fragment(fragment)

    async def get_all_fragments(self) -> List[ExtractedFragment]:
        """Fetch all stored fragments ordered by confidence descending."""
        async with self._lock:
            if not self._conn:
                return []
            cursor = self._conn.cursor()
            cursor.execute("SELECT * FROM fragments ORDER BY confidence_score DESC")
            rows = cursor.fetchall()
            return [self._row_to_fragment(r) for r in rows]

    async def get_fragments_by_round(self, round_id: int) -> List[ExtractedFragment]:
        """Fetch fragments for a specific round."""
        async with self._lock:
            if not self._conn:
                return []
            cursor = self._conn.cursor()
            cursor.execute("SELECT * FROM fragments WHERE round_id = ? ORDER BY confidence_score DESC", (round_id,))
            rows = cursor.fetchall()
            return [self._row_to_fragment(r) for r in rows]

    async def get_fragments_by_category(
        self, category: FragmentCategory
    ) -> List[ExtractedFragment]:
        """Fetch fragments for a category."""
        async with self._lock:
            if not self._conn:
                return []
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT * FROM fragments WHERE category = ? ORDER BY confidence_score DESC",
                (category.value,),
            )
            rows = cursor.fetchall()
            return [self._row_to_fragment(r) for r in rows]

    async def count_fragments(self) -> int:
        """Count total fragments."""
        async with self._lock:
            if not self._conn:
                return 0
            cursor = self._conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM fragments")
            return int(cursor.fetchone()[0])

    async def find_similar_fragments(
        self, query_text: str, top_k: int = 5, min_similarity: float = 0.5
    ) -> List[ExtractedFragment]:
        """Vector similarity search using numpy cosine score."""
        query_vec = await self.embedding_client.get_embedding(query_text)
        async with self._lock:
            if not self._conn:
                return []
            cursor = self._conn.cursor()
            cursor.execute("SELECT * FROM fragments")
            rows = cursor.fetchall()

            scored = []
            for r in rows:
                vec = np.array(json.loads(r["vector_json"]), dtype=np.float32)
                sim = _safe_cosine_similarity(query_vec, vec)
                if sim >= min_similarity:
                    scored.append((sim, self._row_to_fragment(r)))

            scored.sort(key=lambda x: x[0], reverse=True)
            return [item[1] for item in scored[:top_k]]

    async def get_graph(self) -> Dict[str, Any]:
        """Retrieve full graph view: nodes and edges."""
        async with self._lock:
            if not self._conn:
                return {"nodes": [], "edges": []}
            cursor = self._conn.cursor()
            cursor.execute("SELECT fragment_id, category, text, confidence_score, round_id FROM fragments")
            nodes = [
                {
                    "id": r["fragment_id"],
                    "category": r["category"],
                    "text": r["text"],
                    "confidence": r["confidence_score"],
                    "round_id": r["round_id"],
                }
                for r in cursor.fetchall()
            ]

            cursor.execute("SELECT source_id, target_id, relation_type, weight FROM graph_edges")
            edges = [
                {
                    "source": r["source_id"],
                    "target": r["target_id"],
                    "type": r["relation_type"],
                    "weight": r["weight"],
                }
                for r in cursor.fetchall()
            ]
            return {"nodes": nodes, "edges": edges}

    async def clear(self) -> None:
        """Clear database tables."""
        async with self._lock:
            if self._conn:
                cursor = self._conn.cursor()
                cursor.execute("DELETE FROM graph_edges")
                cursor.execute("DELETE FROM fragments")
                self._conn.commit()

    @staticmethod
    def _row_to_fragment(row: sqlite3.Row) -> ExtractedFragment:
        return ExtractedFragment(
            fragment_id=row["fragment_id"],
            round_id=row["round_id"],
            attempt_id=row["attempt_id"],
            category=FragmentCategory(row["category"]),
            text=row["text"],
            confidence_score=row["confidence_score"],
            source_strategy=StrategyCategory(row["source_strategy"]),
            context_snippet=row["context_snippet"],
            timestamp=row["timestamp"],
        )
