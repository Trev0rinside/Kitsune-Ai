"""Abstract Base Class for Reverse-Guardrail fragment and graph storage."""

import abc
from typing import Any, Dict, List, Optional
from reverse_guardrail.core.models import ExtractedFragment, FragmentCategory


class BaseFragmentStore(abc.ABC):
    """Abstract interface for persisting and querying leaked prompt fragments and relationships."""

    @abc.abstractmethod
    async def initialize(self) -> None:
        """Initialize database schema and tables."""
        pass

    @abc.abstractmethod
    async def store_fragment(self, fragment: ExtractedFragment) -> None:
        """Store a single extracted fragment and compute graph relationships."""
        pass

    @abc.abstractmethod
    async def store_fragments(self, fragments: List[ExtractedFragment]) -> None:
        """Store multiple extracted fragments in batch."""
        pass

    @abc.abstractmethod
    async def get_all_fragments(self) -> List[ExtractedFragment]:
        """Retrieve all stored fragments."""
        pass

    @abc.abstractmethod
    async def get_fragments_by_round(self, round_id: int) -> List[ExtractedFragment]:
        """Retrieve fragments extracted in a specific round."""
        pass

    @abc.abstractmethod
    async def get_fragments_by_category(
        self, category: FragmentCategory
    ) -> List[ExtractedFragment]:
        """Retrieve fragments matching a specific classification category."""
        pass

    @abc.abstractmethod
    async def count_fragments(self) -> int:
        """Return total count of stored fragments."""
        pass

    @abc.abstractmethod
    async def find_similar_fragments(
        self, query_text: str, top_k: int = 5, min_similarity: float = 0.5
    ) -> List[ExtractedFragment]:
        """Perform semantic similarity search over stored fragments."""
        pass

    @abc.abstractmethod
    async def get_graph(self) -> Dict[str, Any]:
        """Retrieve nodes and edges representing the fragment relation graph."""
        pass

    @abc.abstractmethod
    async def clear(self) -> None:
        """Clear all stored data (for testing or reset)."""
        pass
