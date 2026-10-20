"""Keyword retrieval (deterministic) with optional LLM reranking."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .agents import RerankAgent
from .index import IndexAgent
from .settings import DocsSettings


@dataclass
class RetrievalResult:
    """A retrieved chunk with its relevance score."""

    chunk_id: str
    document_id: str
    text: str
    score: float
    section: str = ""


class RetrieverAgent:
    """Find the most relevant chunks for a query from an :class:`IndexAgent`."""

    name = "retriever"

    def __init__(
        self,
        settings: DocsSettings | None = None,
        *,
        index: IndexAgent | None = None,
        reranker: RerankAgent | None = None,
    ) -> None:
        self.settings = settings or DocsSettings()
        self.index = index
        self.reranker = reranker

    async def retrieve(
        self, query: str, *, top_k: int | None = None, min_score: float = 0.0
    ) -> list[RetrievalResult]:
        if not self.index:
            raise ValueError("IndexAgent not set. Pass index= to constructor.")
        k = top_k or self.settings.retrieval_k
        results: list[RetrievalResult] = []
        for chunk_id, score in self.index.search_keywords(query, top_k=k * 2):
            if score < min_score:
                continue
            entry = self.index.get_entry(chunk_id)
            if entry:
                results.append(
                    RetrievalResult(
                        chunk_id=entry.chunk_id,
                        document_id=entry.document_id,
                        text=entry.text,
                        score=round(score, 4),
                    )
                )
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:k]

    async def run(self, **kwargs: Any) -> list[RetrievalResult]:
        query = kwargs["query"]
        results = await self.retrieve(query)
        if kwargs.get("rerank", False):
            if self.reranker is None:
                raise ValueError("rerank=True needs a reranker= agent")
            results = await self.reranker.rerank(query, results)
        return results
