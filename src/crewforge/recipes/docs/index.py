"""Keyword / TF-IDF index over chunks (no LLM calls)."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from .ingest import TextChunk

# Common English + Malay stop words.
STOP_WORDS: frozenset[str] = frozenset(
    """
    the a an is are was were be been being have has had do does did will would could
    should may might shall can need must to of in for on with at by from as into about
    between through during before after above below and but or nor not so if then than
    that this these those it its i me my we our you your he him his she her they them
    their dan yang ini itu di ke dari untuk dengan pada adalah akan telah sudah belum
    tidak bukan juga atau tetapi kerana oleh seperti dalam
    """.split()
)


@dataclass
class IndexEntry:
    chunk_id: str
    document_id: str
    text: str
    keywords: list[str] = field(default_factory=list)
    tf_scores: dict[str, float] = field(default_factory=dict)


class IndexAgent:
    """Build a searchable keyword index from chunks. Deterministic."""

    name = "indexer"
    STOP_WORDS = STOP_WORDS

    def __init__(self) -> None:
        self._entries: dict[str, IndexEntry] = {}
        self._idf: dict[str, float] = {}
        self._doc_count = 0

    def _tokenize(self, text: str) -> list[str]:
        words = re.findall(r"[a-zA-Z0-9]{2,}", text.lower())
        return [w for w in words if w not in self.STOP_WORDS and len(w) > 2]

    def _compute_tf(self, words: list[str]) -> dict[str, float]:
        counts = Counter(words)
        total = len(words) or 1
        return {w: c / total for w, c in counts.items()}

    def _compute_idf(self) -> None:
        doc_freq: Counter[str] = Counter()
        for entry in self._entries.values():
            for term in set(entry.tf_scores):
                doc_freq[term] += 1
        n = self._doc_count or 1
        self._idf = {term: math.log((n + 1) / (df + 1)) + 1 for term, df in doc_freq.items()}

    def _extract_keywords(self, tf: dict[str, float], top_n: int = 10) -> list[str]:
        return [term for term, _ in sorted(tf.items(), key=lambda x: x[1], reverse=True)[:top_n]]

    async def index_chunks(self, chunks: list[TextChunk]) -> int:
        """Index chunks; returns how many were indexed."""
        for chunk in chunks:
            tf = self._compute_tf(self._tokenize(chunk.text))
            self._entries[chunk.chunk_id] = IndexEntry(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                text=chunk.text,
                keywords=self._extract_keywords(tf),
                tf_scores=tf,
            )
        self._doc_count = len(self._entries)
        self._compute_idf()
        return len(chunks)

    def compute_tfidf(self, chunk_id: str) -> dict[str, float]:
        entry = self._entries.get(chunk_id)
        if not entry:
            return {}
        return {term: tf * self._idf.get(term, 1.0) for term, tf in entry.tf_scores.items()}

    def search_keywords(self, query: str, top_k: int = 5) -> list[tuple[str, float]]:
        """Rank chunks by TF-IDF overlap with the query; only positive scores."""
        query_words = self._tokenize(query)
        if not query_words:
            return []
        query_tf = self._compute_tf(query_words)
        scores: dict[str, float] = defaultdict(float)
        for entry in self._entries.values():
            score = 0.0
            for word in query_words:
                if word in entry.tf_scores:
                    score += entry.tf_scores[word] * self._idf.get(word, 1.0) * query_tf[word]
            if score > 0:
                scores[entry.chunk_id] = score
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

    def get_entry(self, chunk_id: str) -> IndexEntry | None:
        return self._entries.get(chunk_id)

    def stats(self) -> dict[str, Any]:
        total_keywords = sum(len(e.keywords) for e in self._entries.values())
        return {
            "total_entries": len(self._entries),
            "total_documents": self._doc_count,
            "unique_terms": len(self._idf),
            "avg_keywords_per_chunk": total_keywords / len(self._entries) if self._entries else 0,
        }

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        count = await self.index_chunks(kwargs.get("chunks", []))
        return {"indexed": count, "stats": self.stats()}
