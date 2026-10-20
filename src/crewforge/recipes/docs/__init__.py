"""``docs`` recipe (from documind): ingest documents, then answer questions about
them with ``[Source N]`` citations, optional fact-checking, and summaries.

Ingestion, indexing and keyword retrieval are deterministic (no LLM calls);
the answerer, fact-checker, summarizer, reranker and reference formatter call
the LLM through :class:`crewforge.core.Agent`.
"""

from .agents import (
    Answer,
    AnswerAgent,
    CitationAgent,
    FactCheckAgent,
    FactCheckResult,
    FormattedCitation,
    RerankAgent,
    SummarizerAgent,
    Summary,
)
from .export import ExportAgent
from .index import IndexAgent, IndexEntry
from .ingest import Document, IngestAgent, TextChunk
from .pipeline import DocsPipeline, PipelineResult
from .retrieve import RetrievalResult, RetrieverAgent
from .settings import DocsSettings

__all__ = [
    "Answer",
    "AnswerAgent",
    "CitationAgent",
    "DocsPipeline",
    "DocsSettings",
    "Document",
    "ExportAgent",
    "FactCheckAgent",
    "FactCheckResult",
    "FormattedCitation",
    "IndexAgent",
    "IndexEntry",
    "IngestAgent",
    "PipelineResult",
    "RerankAgent",
    "RetrievalResult",
    "RetrieverAgent",
    "SummarizerAgent",
    "Summary",
    "TextChunk",
]
