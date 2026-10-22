"""Document Q&A pipeline: ingest → index → retrieve → answer (→ fact-check), summarize.

Ingestion, indexing and keyword retrieval never touch the network, so
``ingest`` works without an API key. The LLM crew is created lazily the first
time an answer, summary or rerank is needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

import httpx

from ...core.agent import Agent
from ...core.client import LLMClient
from ...core.config import LLMConfig
from ...core.crew import Crew
from ...core.errors import AgentFailure, CrewFailedError
from ...core.usage import UsageTracker
from .agents import (
    Answer,
    AnswerAgent,
    CitationAgent,
    FactCheckAgent,
    FactCheckResult,
    RerankAgent,
    SummarizerAgent,
    Summary,
)
from .export import ExportAgent
from .index import IndexAgent
from .ingest import Document, IngestAgent, TextChunk
from .retrieve import RetrievalResult, RetrieverAgent
from .settings import DocsSettings

A = TypeVar("A", bound=Agent)


@dataclass
class PipelineResult:
    """Result of :meth:`DocsPipeline.run_full`."""

    document: Document
    summary: Summary | None
    answers: list[Answer] = field(default_factory=list)
    export_path: str = ""
    token_summary: dict[str, Any] = field(default_factory=dict)


class DocsPipeline:
    """Orchestrates the document agents on one lazily created crew."""

    def __init__(
        self,
        config: LLMConfig | None = None,
        settings: DocsSettings | None = None,
        *,
        client: LLMClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config or LLMConfig()
        self.settings = settings or DocsSettings()
        self._client = client
        self._transport = transport
        self._crew: Crew | None = None
        self._llm_agents: dict[str, Agent] = {}
        self.tracker = UsageTracker()

        self.ingester = IngestAgent(self.settings)
        self.indexer = IndexAgent()
        self.retriever = RetrieverAgent(self.settings, index=self.indexer)
        self.exporter = ExportAgent()

        self._documents: list[Document] = []
        self._chunks: list[TextChunk] = []
        self._session_answers: list[Answer] = []

    # -- crew ---------------------------------------------------------------------

    @property
    def crew(self) -> Crew:
        """The LLM crew; validates the provider config on first use."""
        if self._crew is None:
            self._crew = Crew(
                "docs",
                self.config,
                client=self._client,
                tracker=self.tracker,
                transport=self._transport,
            )
            self.retriever.reranker = self._crew.agent(RerankAgent)
        return self._crew

    def _llm_agent(self, cls: type[A], **kwargs: Any) -> A:
        agent = self._llm_agents.get(cls.name)
        if isinstance(agent, cls):
            return agent
        created = self._llm_agents[cls.name] = self.crew.agent(cls, **kwargs)
        return created

    @property
    def answerer(self) -> AnswerAgent:
        return self._llm_agent(AnswerAgent)

    @property
    def fact_checker(self) -> FactCheckAgent:
        return self._llm_agent(FactCheckAgent)

    @property
    def summarizer(self) -> SummarizerAgent:
        return self._llm_agent(SummarizerAgent)

    @property
    def citation_agent(self) -> CitationAgent:
        return self._llm_agent(CitationAgent, citation_format=self.settings.citation_format)

    def require_llm(self) -> Crew:
        """Create the crew now so a bad provider config fails before any work."""
        return self.crew

    async def close(self) -> None:
        self.tracker.finish()
        if self._crew is not None:
            await self._crew.__aexit__(None, None, None)

    async def __aenter__(self) -> DocsPipeline:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # -- ingest -------------------------------------------------------------------

    async def ingest_documents(self, paths: list[str | Path]) -> list[Document]:
        docs = []
        for p in paths:
            doc = await self.ingester.run(p)
            docs.append(doc)
            self._chunks.extend(doc.chunks)
        self._documents.extend(docs)
        if self._chunks:
            await self.indexer.index_chunks(self._chunks)
        return docs

    async def ingest_text(self, text: str, name: str = "document") -> Document:
        """Ingest raw text (written to a temp file so the normal parser runs)."""
        import os
        import tempfile

        fd, tmp = tempfile.mkstemp(suffix=".txt", prefix=f"{name}_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
            doc = await self.ingester.run(tmp)
        finally:
            os.unlink(tmp)
        self._documents.append(doc)
        self._chunks.extend(doc.chunks)
        await self.indexer.index_chunks(doc.chunks)
        return doc

    # -- Q&A ----------------------------------------------------------------------

    async def _retrieve(self, question: str, rerank: bool) -> list[RetrievalResult]:
        crew = self.crew
        chunks = await self.retriever.retrieve(question)
        if not chunks:
            # Honest failure: never ask the model to answer from an empty context.
            failure = AgentFailure(
                "retriever",
                f"no passage in the documents matches the question {question!r}",
                "empty",
            )
            crew.failures.append(failure)
            raise CrewFailedError(crew.name, [failure])
        if rerank:
            reranker = self.retriever.reranker
            assert reranker is not None  # attached by the crew property above
            chunks = await crew.step("reranker", reranker.rerank(question, chunks))
        return chunks

    async def ask(self, question: str, rerank: bool = False) -> Answer:
        chunks = await self._retrieve(question, rerank)
        answer = await self.crew.step(self.answerer, self.answerer.answer(question, chunks))
        self._session_answers.append(answer)
        return answer

    async def ask_with_verification(
        self, question: str, rerank: bool = False
    ) -> tuple[Answer, FactCheckResult]:
        chunks = await self._retrieve(question, rerank)
        answer = await self.crew.step(self.answerer, self.answerer.answer(question, chunks))
        check = await self.crew.step(self.fact_checker, self.fact_checker.check(answer, chunks))
        self._session_answers.append(answer)
        self.exporter.checks[id(answer)] = check
        return answer, check

    async def summarize_document(self, doc: Document, max_length: str = "medium") -> Summary:
        summarizer = self.crew.agent(SummarizerAgent)
        return await self.crew.step(summarizer, summarizer.summarize(doc, max_length=max_length))

    async def export_session(self, path: str | Path, fmt: str = "markdown") -> str:
        if not self._session_answers:
            return ""
        out = await self.exporter.export_session(self._session_answers, path, format=fmt)
        return str(out)

    async def run_full(self, doc_path: str | Path, questions: list[str] | None = None):
        """Ingest one document, summarize it and answer ``questions``."""
        try:
            (doc,) = await self.ingest_documents([doc_path])
            summary = await self.summarize_document(doc)
            answers = [await self.ask(q) for q in questions or []]
            export_path = ""
            if answers:
                export_path = await self.export_session(
                    Path("output") / f"crewforge-docs-{doc.doc_id}.md"
                )
        finally:
            await self.close()
        return PipelineResult(
            document=doc,
            summary=summary,
            answers=answers,
            export_path=export_path,
            token_summary=self.tracker.summary(),
        )
