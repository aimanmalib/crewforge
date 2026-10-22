"""The academic crew: ``plan``, ``feedback`` and ``cite`` runs.

The agents produce JSON; this module applies the deterministic rules on top:
the word budget is computed here (not trusted from the model), feedback quotes
are checked against the draft and long suggestions are cut back to comments,
model-proposed sources go through :func:`citations.check_source`, and the
formatter may neither skip nor add references.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from ...core.client import LLMClient
from ...core.config import LLMConfig
from ...core.crew import Crew
from ...core.errors import OutputParseError
from ...core.usage import UsageTracker
from .agents import (
    FEEDBACK_AGENTS,
    BriefAgent,
    BriefInfo,
    FeedbackOutput,
    FormattedRef,
    FormatterAgent,
    PlannerAgent,
    PlanOutput,
)
from .citations import DraftCitations, SourceCheck, analyse_draft, check_formatted, check_source
from .language import indonesian_forms

logger = logging.getLogger(__name__)


def allocate_words(proposed: list[int], target: int | None) -> list[int]:
    """Scale the planner's section budgets so they add up to ``target`` exactly.

    Models are poor at arithmetic, so the total is enforced here. Budgets are
    rounded to tens for targets of reasonable size; any rounding remainder goes
    to the largest section. Without a target the planner's numbers are kept.
    """
    if not proposed:
        return []
    if target is None:
        return list(proposed)
    weights = proposed if sum(proposed) > 0 else [1] * len(proposed)
    total = sum(weights)
    raw = [target * w / total for w in weights]
    unit = 10 if target >= 50 * len(proposed) else 1
    budget = [int(round(r / unit)) * unit for r in raw]
    largest = max(range(len(raw)), key=raw.__getitem__)
    budget[largest] += target - sum(budget)
    return budget


def paragraphs(text: str) -> list[str]:
    """Blank-line separated paragraphs (the unit feedback comments point at)."""
    return [p.strip() for p in re.split(r"\n\s*\n", text.replace("\r\n", "\n")) if p.strip()]


def number_paragraphs(paras: list[str]) -> str:
    return "\n\n".join(f"[P{i}] {p}" for i, p in enumerate(paras, start=1))


_QUOTE_MARKS = "\"'“”‘’«»"


def _norm(text: str) -> str:
    return " ".join(text.casefold().split())


def quote_in(quote: str, text: str) -> bool:
    """Whether ``quote`` (allowing "..." elisions and stray quote marks) occurs in ``text``."""
    pieces = [p.strip(_QUOTE_MARKS + " ") for p in re.split(r"\.\.\.|…", quote)]
    pieces = [_norm(p) for p in pieces if p.strip(_QUOTE_MARKS + " .")]
    if not pieces:
        return True
    haystack = _norm(text)
    return all(p in haystack for p in pieces)


def trim_words(text: str, limit: int) -> tuple[str, bool]:
    words = text.split()
    if len(words) <= limit:
        return text, False
    return " ".join(words[:limit]) + " …", True


# --- plan ---------------------------------------------------------------------


@dataclass
class PlanResult:
    brief: BriefInfo
    plan: PlanOutput
    style: str
    language: str
    target_words: int | None
    budget: list[int]
    readings: list[SourceCheck]
    reading_notes: list[str]
    malay_issues: dict[str, str] = field(default_factory=dict)
    tracker: UsageTracker | None = field(default=None, repr=False)

    def counts(self) -> dict[str, int]:
        return {
            "research_questions": len(self.plan.research_questions),
            "sections": len(self.plan.outline),
            "suggested_readings": len(self.readings),
            "flagged_readings": sum(1 for r in self.readings if r.status == "flagged"),
        }


# --- feedback -----------------------------------------------------------------


@dataclass
class FeedbackComment:
    reviewer: str
    paragraph: int | None
    quote: str
    issue: str
    suggestion: str
    severity: str
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class FeedbackResult:
    name: str
    language: str
    style: str
    paragraph_count: int
    reviews: dict[str, FeedbackOutput]
    comments: list[FeedbackComment]
    citations: DraftCitations
    failed: dict[str, str] = field(default_factory=dict)
    malay_issues: dict[str, str] = field(default_factory=dict)
    tracker: UsageTracker | None = field(default=None, repr=False)

    def counts(self) -> dict[str, int]:
        return {"comments": len(self.comments), "paragraphs": self.paragraph_count}


# --- cite ---------------------------------------------------------------------


@dataclass
class CitedRef:
    index: int
    original: str
    formatted: str
    missing: list[str]
    note: str
    check: SourceCheck


@dataclass
class CiteResult:
    style: str
    language: str
    refs: list[CitedRef]
    discarded: list[FormattedRef] = field(default_factory=list)
    tracker: UsageTracker | None = field(default=None, repr=False)

    def counts(self) -> dict[str, int]:
        return {"references": len(self.refs), "discarded": len(self.discarded)}


class AcademicCrew:
    """Runs one academic step on a shared client and usage tracker."""

    def __init__(
        self,
        config: LLMConfig,
        *,
        language: str = "en",
        max_suggestion_words: int = 60,
        client: LLMClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        self.language = language
        self.max_suggestion_words = max_suggestion_words
        self._client = client
        self._transport = transport

    def _crew(self) -> Crew:
        return Crew("academic", self.config, client=self._client, transport=self._transport)

    def _malay_check(self, texts: list[str]) -> dict[str, str]:
        if self.language != "ms":
            return {}
        return indonesian_forms("\n".join(texts))

    async def plan(
        self, brief_text: str, *, words: int | None = None, style: str | None = None
    ) -> PlanResult:
        async with self._crew() as crew:
            brief_agent = crew.agent(BriefAgent)
            brief = await crew.step(brief_agent, brief_agent.execute(brief_text, self.language))
            target = words or brief.word_count
            chosen_style = style or brief.citation_style or "apa"
            planner = crew.agent(PlannerAgent)
            plan = await crew.step(
                planner, planner.execute(brief, brief_text, target, chosen_style, self.language)
            )
        readings = [check_source(r.reference, "model") for r in plan.suggested_readings]
        notes = [r.why for r in plan.suggested_readings]
        written = [plan.working_title, *plan.research_questions, *plan.search_queries]
        for s in plan.outline:
            written += [s.heading, s.purpose, *s.key_points]
        for n in plan.source_needs:
            written += [n.need, n.why, n.where_to_look]
        return PlanResult(
            brief=brief,
            plan=plan,
            style=chosen_style,
            language=self.language,
            target_words=target,
            budget=allocate_words([s.words for s in plan.outline], target),
            readings=readings,
            reading_notes=notes,
            malay_issues=self._malay_check(written + notes),
            tracker=crew.tracker,
        )

    async def feedback(
        self,
        draft_text: str,
        *,
        name: str = "draft",
        brief_text: str = "",
        style: str = "apa",
        reviewers: list[str] | None = None,
        allow_partial: bool = False,
    ) -> FeedbackResult:
        names = list(reviewers or FEEDBACK_AGENTS)
        unknown = [n for n in names if n not in FEEDBACK_AGENTS]
        if unknown:
            raise ValueError(f"unknown reviewer(s): {', '.join(unknown)}")
        paras = paragraphs(draft_text)
        numbered = number_paragraphs(paras)
        async with self._crew() as crew:
            work = {
                n: crew.agent(FEEDBACK_AGENTS[n]).execute(
                    numbered, self.language, brief_text, style
                )
                for n in names
            }
            done = await crew.parallel(work, require="any" if allow_partial else "all")
        comments: list[FeedbackComment] = []
        for reviewer in names:
            if reviewer not in done:
                continue
            for c in done[reviewer].comments:
                comments.append(self._checked_comment(reviewer, c, paras))
        comments.sort(key=lambda c: (c.paragraph or 0, c.severity != "major", c.reviewer))
        written = []
        for review in done.values():
            written += [review.summary, *review.strengths]
        written += [x for c in comments for x in (c.issue, c.suggestion)]
        return FeedbackResult(
            name=name,
            language=self.language,
            style=style,
            paragraph_count=len(paras),
            reviews={n: done[n] for n in names if n in done},
            comments=comments,
            citations=analyse_draft(draft_text),
            failed={f.agent: f.error for f in crew.failures},
            malay_issues=self._malay_check(written),
            tracker=crew.tracker,
        )

    def _checked_comment(self, reviewer: str, c: Any, paras: list[str]) -> FeedbackComment:
        flags: list[str] = []
        paragraph = c.paragraph
        if paragraph is not None and not 1 <= paragraph <= len(paras):
            flags.append("paragraph_out_of_range")
            paragraph = None
        if c.quote and not (paragraph and quote_in(c.quote, paras[paragraph - 1])):
            # Point at the paragraph that really holds the quote, if any does.
            found = next((i for i, p in enumerate(paras, start=1) if quote_in(c.quote, p)), None)
            if found is not None:
                paragraph = found
                if "paragraph_out_of_range" in flags:
                    flags.remove("paragraph_out_of_range")
            else:
                flags.append("quote_not_found")
        suggestion, trimmed = trim_words(c.suggestion, self.max_suggestion_words)
        if trimmed:
            flags.append("suggestion_trimmed")
        return FeedbackComment(
            reviewer=reviewer,
            paragraph=paragraph,
            quote=c.quote,
            issue=c.issue,
            suggestion=suggestion,
            severity=c.severity,
            flags=flags,
        )

    async def cite(self, references: list[str], *, style: str = "apa") -> CiteResult:
        if not references:
            raise ValueError("no references to format")
        async with self._crew() as crew:
            formatter = crew.agent(FormatterAgent)

            async def _format() -> tuple[dict[int, FormattedRef], list[FormattedRef]]:
                output = await formatter.execute(references, style, self.language)
                return _match_indices(output.references, len(references))

            matched, discarded = await crew.step(formatter, _format())
        refs = [
            CitedRef(
                index=i,
                original=references[i - 1],
                formatted=matched[i].formatted,
                missing=matched[i].missing,
                note=matched[i].note,
                check=check_formatted(references[i - 1], matched[i].formatted),
            )
            for i in range(1, len(references) + 1)
        ]
        if style in ("apa", "harvard"):
            refs.sort(key=lambda r: r.formatted.casefold())
        return CiteResult(style, self.language, refs, discarded, tracker=crew.tracker)


def _match_indices(
    items: list[FormattedRef], expected: int
) -> tuple[dict[int, FormattedRef], list[FormattedRef]]:
    """One formatted entry per supplied reference; anything else is discarded.

    A skipped reference fails the run naming the formatter: a reference list
    that silently lost an entry is worse than no list.
    """
    matched: dict[int, FormattedRef] = {}
    discarded: list[FormattedRef] = []
    for item in items:
        if 1 <= item.index <= expected and item.index not in matched:
            matched[item.index] = item
        else:
            discarded.append(item)
    missing = [i for i in range(1, expected + 1) if i not in matched]
    if missing:
        raise OutputParseError(
            "formatter", f"skipped supplied reference(s) {', '.join(map(str, missing))}"
        )
    return matched, discarded
