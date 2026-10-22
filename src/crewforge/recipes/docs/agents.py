"""LLM agents of the ``docs`` recipe: answer, fact-check, summarize, rerank, cite."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ...core.agent import Agent
from ...core.errors import OutputParseError
from ...core.parsing import extract_json

if TYPE_CHECKING:
    from .ingest import Document
    from .retrieve import RetrievalResult


def _excerpt(text: str, limit: int = 120) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


# --------------------------------------------------------------------------- answer


@dataclass
class Answer:
    """An answer with the sources it actually cited."""

    question: str
    answer_text: str
    citations: list[dict[str, str]]
    confidence: str = "medium"
    reasoning: str = ""


class AnswerAgent(Agent):
    """Answer strictly from retrieved passages, citing them as ``[Source N]``."""

    name = "answerer"
    description = "Answers from retrieved passages with [Source N] citations"
    system_prompt = (
        "You are the answer agent of a document Q&A crew. You answer questions STRICTLY "
        "based on the provided document excerpts. If the answer is not in the provided "
        "context, say so clearly. Always cite your sources using [Source N] notation. "
        "Be precise, factual, and concise."
    )

    LEVELS = {
        "brief": "Give a brief 1-2 sentence answer.",
        "normal": "Give a clear, complete answer in a paragraph.",
        "detailed": "Give a detailed answer with explanation and context.",
    }

    def _build_context(self, chunks: list[RetrievalResult]) -> str:
        return "\n\n---\n\n".join(
            f"[Source {i + 1}] (doc: {c.document_id}, chunk: {c.chunk_id})\n{c.text}"
            for i, c in enumerate(chunks)
        )

    async def answer(
        self, question: str, chunks: list[RetrievalResult], *, detail_level: str = "normal"
    ) -> Answer:
        level = self.LEVELS.get(detail_level, "Give a clear, complete answer.")
        prompt = (
            "Based on the following document excerpts, answer this question:\n\n"
            f"Question: {question}\n\n"
            f"Document excerpts:\n{self._build_context(chunks)}\n\n"
            f"Instructions: {level}\n"
            "Include [Source N] citations in your answer. "
            "End with a line 'Confidence: high|medium|low'."
        )
        response = await self.ask(prompt)
        content = response.content

        citations = [
            {
                "source_num": str(i + 1),
                "chunk_id": c.chunk_id,
                "document_id": c.document_id,
                "excerpt": c.text[:200],
            }
            for i, c in enumerate(chunks)
            if f"[Source {i + 1}]" in content
        ]
        confidence = "medium"
        match = re.search(
            r"confidence(?:\s+level)?\s*[:=]\s*\**\s*(high|medium|low)", content, re.I
        )
        if match:
            confidence = match.group(1).lower()
        return Answer(
            question=question,
            answer_text=content,
            citations=citations,
            confidence=confidence,
            reasoning=response.reasoning,
        )

    async def run(self, **kwargs: Any) -> Answer:
        return await self.answer(
            kwargs["question"], kwargs["chunks"], detail_level=kwargs.get("detail_level", "normal")
        )


# ----------------------------------------------------------------------- fact-check

VERDICTS = ("verified", "partially_verified", "unverified", "contradicted")
_CLAIM_TOKEN = re.compile(r"\b(VERIFIED|UNVERIFIED|CONTRADICTED)\b", re.I)
_OVERALL = re.compile(r"OVERALL\s*[:=]\s*[\*\[\s]*([A-Za-z_ -]+)", re.I)


def _normalize_verdict(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    v = re.sub(r"[\s-]+", "_", value.strip().strip("[]*.").lower())
    return v if v in VERDICTS else None


def _derive_overall(verdicts: list[str]) -> str:
    verified = verdicts.count("verified")
    if "contradicted" in verdicts:
        return "partially_verified" if verified else "contradicted"
    if "unverified" in verdicts:
        return "partially_verified" if verified else "unverified"
    return "verified"


@dataclass
class FactCheckResult:
    """Result of checking an answer's claims against its sources."""

    overall_verdict: str  # verified | partially_verified | unverified | contradicted
    claims_checked: int
    claims_verified: int
    claims_contradicted: int
    issues: list[str]
    details: str
    claims: list[dict[str, Any]] = field(default_factory=list)


class FactCheckAgent(Agent):
    """Verify each claim of an answer against the source passages."""

    name = "fact_checker"
    description = "Checks each claim of an answer against the cited passages"
    temperature = 0.0
    system_prompt = (
        "You are the fact-checking agent of a document Q&A crew. Compare the claims in an "
        "answer against source documents. For each claim decide: VERIFIED (supported by a "
        "source), UNVERIFIED (not found in the sources) or CONTRADICTED (conflicts with a "
        "source). Be strict and precise. Reply with ONE JSON object and nothing else:\n"
        '{"claims": [{"claim": "...", "verdict": "verified|unverified|contradicted", '
        '"source": "Source N"}], "overall": "verified|partially_verified|unverified|contradicted"}'
    )

    def parse(self, content: str) -> FactCheckResult:
        """JSON verdict first; else documind's ``OVERALL: <verdict>`` text format."""
        data = extract_json(content)
        if isinstance(data, dict) and ("claims" in data or "overall" in data):
            raw_claims = data.get("claims") or []
            if not isinstance(raw_claims, list):
                raise OutputParseError(self.name, "'claims' is not a list", _excerpt(content))
            claims: list[dict[str, Any]] = []
            for item in raw_claims:
                verdict = (
                    _normalize_verdict(item.get("verdict")) if isinstance(item, dict) else None
                )
                if verdict is None or verdict == "partially_verified":
                    raise OutputParseError(
                        self.name, f"claim without a valid verdict: {item!r}", _excerpt(content)
                    )
                claims.append({**item, "verdict": verdict})
            verdicts = [c["verdict"] for c in claims]
            overall = data.get("overall")
            if overall is None:
                if not verdicts:
                    raise OutputParseError(self.name, "no claims and no overall verdict")
                overall_verdict = _derive_overall(verdicts)
            else:
                normalized = _normalize_verdict(overall)
                if normalized is None:
                    raise OutputParseError(self.name, f"unknown overall verdict {overall!r}")
                overall_verdict = normalized
            issues = [
                f"{c['verdict'].upper()}: {c.get('claim', '')}".strip()
                for c in claims
                if c["verdict"] != "verified"
            ]
        else:
            match = _OVERALL.search(content)
            parsed = _normalize_verdict(match.group(1)) if match else None
            if parsed is None:
                raise OutputParseError(
                    self.name,
                    "no JSON verdict and no 'OVERALL: <verdict>' line",
                    _excerpt(content),
                )
            overall_verdict = parsed
            verdicts, issues = [], []
            for line in content.splitlines():
                if _OVERALL.search(line):
                    continue
                found = [t.lower() for t in _CLAIM_TOKEN.findall(line)]
                verdicts.extend(found)
                if any(t != "verified" for t in found):
                    issues.append(line.strip())
            claims = []

        return FactCheckResult(
            overall_verdict=overall_verdict,
            claims_checked=len(verdicts),
            claims_verified=verdicts.count("verified"),
            claims_contradicted=verdicts.count("contradicted"),
            issues=issues[:10],
            details=content,
            claims=claims,
        )

    async def check(self, answer: Answer, source_chunks: list[RetrievalResult]) -> FactCheckResult:
        sources = "\n\n".join(f"[Source {i + 1}]: {c.text}" for i, c in enumerate(source_chunks))
        prompt = (
            "Fact-check this answer against the source documents.\n\n"
            f"Answer: {answer.answer_text}\n\nSources:\n{sources}\n\n"
            "List each factual claim with its verdict, as the JSON object described."
        )
        response = await self.ask(prompt)
        return self.parse(response.content)

    async def run(self, **kwargs: Any) -> FactCheckResult:
        return await self.check(kwargs["answer"], kwargs["source_chunks"])


# ------------------------------------------------------------------------ summarize


@dataclass
class Summary:
    document_id: str
    filename: str
    summary_text: str
    key_points: list[str]
    word_count: int
    compression_ratio: float
    truncated: bool = False  # True when only the first MAX_CHARS were summarized


class SummarizerAgent(Agent):
    """Summarize a whole document and pull out its key points."""

    name = "summarizer"
    description = "Summarizes a document and lists its key points"
    system_prompt = (
        "You are the summarization agent of a document crew. Create clear, accurate "
        "summaries that capture the main ideas and key points. Use bullet points for key "
        "takeaways."
    )
    MAX_CHARS = 12000
    LENGTHS = {
        "short": "3-5 sentences",
        "medium": "1-2 paragraphs",
        "long": "3-4 paragraphs with detailed key points",
    }

    async def summarize(self, document: Document, *, max_length: str = "medium") -> Summary:
        content = document.content
        truncated = len(content) > self.MAX_CHARS
        if truncated:
            content = content[: self.MAX_CHARS] + "\n...[truncated]"
        length = self.LENGTHS.get(max_length, "1-2 paragraphs")
        prompt = (
            f"Summarize the following document in {length}. "
            "After the summary, list 3-7 key points as bullet points starting with '•'.\n\n"
            f"Document: {document.filename}\n{content}"
        )
        response = await self.ask(prompt)
        text = response.content
        key_points = []
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.startswith(("•", "- ", "* ")):
                point = stripped.lstrip("•-* ").strip()
                if point:
                    key_points.append(point)
        words = len(text.split())
        return Summary(
            document_id=document.doc_id,
            filename=document.filename,
            summary_text=text,
            key_points=key_points,
            word_count=words,
            compression_ratio=round(words / max(document.total_words, 1), 3),
            truncated=truncated,
        )

    async def run(self, **kwargs: Any) -> Summary:
        return await self.summarize(
            kwargs["document"], max_length=kwargs.get("max_length", "medium")
        )


# --------------------------------------------------------------------------- rerank


class RerankAgent(Agent):
    """Reorder keyword-retrieved passages by semantic relevance."""

    name = "reranker"
    description = "Reorders retrieved passages by relevance to the question"
    temperature = 0.0
    system_prompt = (
        "You rank text passages by how well they answer a question. "
        "Reply with the passage indices only, most relevant first, comma-separated."
    )

    def parse(self, content: str, count: int) -> list[int]:
        """Indices from ``"2, 0, 1"`` or a JSON list; anything else is a parse error."""
        data = extract_json(content)
        if isinstance(data, dict):
            data = data.get("ranking") or data.get("indices")
        raw = data if isinstance(data, list) else re.findall(r"-?\d+", content)
        try:
            indices = [int(x) for x in raw]
        except (TypeError, ValueError):
            indices = []
        ordered: list[int] = []
        for i in indices:
            if 0 <= i < count and i not in ordered:
                ordered.append(i)
        if not ordered:
            raise OutputParseError(
                self.name, f"no valid passage index (0..{count - 1})", _excerpt(content)
            )
        return ordered

    async def rerank(
        self, query: str, candidates: list[RetrievalResult], top_k: int | None = None
    ) -> list[RetrievalResult]:
        if not candidates:
            return []
        context = "\n\n".join(f"[{i}] {c.text[:300]}" for i, c in enumerate(candidates))
        prompt = (
            f'Given the question: "{query}"\n\n'
            "Rank these text chunks by relevance (most relevant first). "
            f"Return ONLY the indices in order, comma-separated.\n\n{context}"
        )
        response = await self.ask(prompt)
        order = self.parse(response.content, len(candidates))
        ranked = [candidates[i] for i in order]
        # Passages the model left out keep their keyword order after the ranked ones.
        ranked += [c for i, c in enumerate(candidates) if i not in order]
        return ranked[: top_k or len(candidates)]


# ------------------------------------------------------------------------- citation


@dataclass
class FormattedCitation:
    style: str
    inline: str
    full_reference: str
    source_num: int


class CitationAgent(Agent):
    """Format citations locally (APA/MLA/Chicago) or ask the LLM for a reference list."""

    name = "citation"
    description = "Formats citations and reference lists"

    def __init__(self, *args: Any, citation_format: str = "apa", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.citation_format = citation_format

    def _format_apa(self, title: str, author: str, year: str, n: int) -> FormattedCitation:
        return FormattedCitation("apa", f"({author}, {year})", f"{author} ({year}). {title}.", n)

    def _format_mla(self, title: str, author: str, year: str, n: int) -> FormattedCitation:
        return FormattedCitation("mla", f"({author})", f'{author}. "{title}." {year}.', n)

    def _format_chicago(self, title: str, author: str, year: str, n: int) -> FormattedCitation:
        return FormattedCitation(
            "chicago", f"({author} {year})", f'{author}. "{title}." {year}.', n
        )

    def format_citation(
        self,
        title: str,
        author: str = "Document",
        year: str = "n.d.",
        style: str | None = None,
        source_num: int = 1,
    ) -> FormattedCitation:
        formatter = {
            "apa": self._format_apa,
            "mla": self._format_mla,
            "chicago": self._format_chicago,
        }.get(style or self.citation_format, self._format_apa)
        return formatter(title, author, year, source_num)

    async def generate_references(
        self, citations: list[dict[str, str]], style: str | None = None
    ) -> str:
        if not citations:
            return "No sources cited."
        sources = "\n".join(
            f"Source {c.get('source_num', i + 1)}: chunk={c.get('chunk_id', '?')}, "
            f"doc={c.get('document_id', '?')}, excerpt={c.get('excerpt', '')[:100]}"
            for i, c in enumerate(citations)
        )
        fmt = (style or self.citation_format).upper()
        response = await self.ask(
            f"Format these sources as a {fmt} reference list:\n\n{sources}\n\n"
            f"Use proper {fmt} formatting. Number each entry."
        )
        return response.content

    async def run(self, **kwargs: Any) -> Any:
        if "citations" in kwargs:
            return await self.generate_references(kwargs["citations"], kwargs.get("style"))
        return self.format_citation(
            title=kwargs.get("title", "Untitled"),
            author=kwargs.get("author", "Document"),
            year=kwargs.get("year", "n.d."),
            style=kwargs.get("style"),
            source_num=kwargs.get("source_num", 1),
        )
