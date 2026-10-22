"""Agents of the academic recipe and the JSON each one must return.

None of these agents writes the student's assignment. The brief and planner
agents plan; the four feedback agents comment on the student's own draft; the
formatter formats references the student supplied. Every agent must answer
with JSON matching its schema; empty, prose or wrongly shaped replies fail the
run naming the agent (the core ``Agent.ask`` / ``parse_json`` guards).
"""

from __future__ import annotations

import re
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

from ...core.agent import Agent
from ...core.parsing import parse_json
from .language import llm_instruction

STYLES = ("apa", "ieee", "harvard")
STYLE_GUIDE = {
    "apa": "APA 7th edition (author-date; reference list in alphabetical order)",
    "ieee": "IEEE (numbered [n] in order of first citation)",
    "harvard": "Harvard (author-date; reference list in alphabetical order)",
}


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _texts(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]
    out = []
    for item in value:
        if isinstance(item, dict):
            item = next((v for v in item.values() if isinstance(v, str) and v.strip()), "")
        if _text(item):
            out.append(_text(item))
    return out


_HEADING_NUMBER = re.compile(r"^\s*(?:\d+(?:\.\d+)+|\d+[.)]|[IVX]+\.)\s+")
_REF_NUMBER = re.compile(r"^\s*(?:\[\d+\]|\d+[.)])\s*")
_HTML_ITALIC = re.compile(r"<(em|i)>(.*?)</\1>", re.IGNORECASE | re.DOTALL)


def _heading(value: Any) -> str:
    """The table numbers sections itself; drop the model's own "1." / "2.1" prefix."""
    return _HEADING_NUMBER.sub("", _text(value), count=1)


def _reference(value: Any) -> str:
    """Formatted references: no model numbering (IEEE numbers are added by the code),
    and Markdown italics instead of the HTML some models emit."""
    text = _REF_NUMBER.sub("", _text(value), count=1)
    return _HTML_ITALIC.sub(lambda m: f"*{m.group(2)}*", text)


Text = Annotated[str, BeforeValidator(_text)]
Texts = Annotated[list[str], BeforeValidator(_texts)]
Heading = Annotated[str, BeforeValidator(_heading)]
Reference = Annotated[str, BeforeValidator(_reference)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore")


# --- plan ---------------------------------------------------------------------


class RubricItem(_Model):
    criterion: Text = Field(min_length=1)
    weight: float | None = None

    @field_validator("weight", mode="before")
    @classmethod
    def _percent(cls, value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(str(value).strip().rstrip("%"))
        except ValueError:
            return None


class BriefInfo(_Model):
    """What the brief agent extracts. ``title`` is required."""

    title: Text = Field(min_length=1)
    course: Text = ""
    level: Text = ""
    word_count: int | None = Field(default=None, ge=1)
    citation_style: str | None = None
    deadline: Text = ""
    requirements: Texts = Field(default_factory=list)
    rubric: list[RubricItem] = Field(default_factory=list)
    keywords: Texts = Field(default_factory=list)

    @field_validator("word_count", mode="before")
    @classmethod
    def _int_or_none(cls, value: Any) -> int | None:
        if value in (None, "", 0):
            return None
        try:
            return int(str(value).replace(",", "").split()[0])
        except (ValueError, IndexError):
            return None

    @field_validator("citation_style", mode="before")
    @classmethod
    def _style(cls, value: Any) -> str | None:
        text = _text(value).lower()
        return next((s for s in STYLES if s in text), None)


class Section(_Model):
    heading: Heading = Field(min_length=1)
    purpose: Text = ""
    key_points: Texts = Field(default_factory=list)
    words: int = Field(default=0, ge=0)

    @field_validator("words", mode="before")
    @classmethod
    def _words(cls, value: Any) -> int:
        try:
            return max(0, int(float(str(value or 0).replace(",", ""))))
        except ValueError:
            return 0


class SourceNeed(_Model):
    need: Text = Field(min_length=1)
    why: Text = ""
    where_to_look: Text = ""


class Reading(_Model):
    reference: Text = Field(min_length=1)
    why: Text = ""


class PlanOutput(_Model):
    """What the planner must return: at least one question and one section."""

    working_title: Text = ""
    research_questions: Texts = Field(min_length=1)
    outline: list[Section] = Field(min_length=1)
    source_needs: list[SourceNeed] = Field(default_factory=list)
    search_queries: Texts = Field(default_factory=list)
    suggested_readings: list[Reading] = Field(default_factory=list)


class BriefAgent(Agent):
    name = "brief"
    description = "Extracts the requirements from an assignment brief"
    temperature = 0.1
    system_prompt = (
        "You read assignment briefs for students. Extract what the brief asks for; do "
        "not add requirements it does not state.\n"
        "Reply with ONE JSON object and nothing else, exactly this shape:\n"
        '{"title": "assignment title or topic", "course": "", "level": "", '
        '"word_count": 1500 or null, "citation_style": "APA|IEEE|Harvard|other" or null, '
        '"deadline": "", "requirements": ["..."], '
        '"rubric": [{"criterion": "...", "weight": 30}], "keywords": ["..."]}\n'
        "Use null or empty values for anything the brief does not say."
    )

    async def execute(self, brief_text: str, language: str) -> BriefInfo:
        response = await self.ask(
            f"ASSIGNMENT BRIEF:\n{brief_text}\n\nReturn the JSON object.",
            system=f"{self.system_prompt}\n{llm_instruction(language)}",
        )
        return parse_json(response.content, agent=self.name, schema=BriefInfo)


class PlannerAgent(Agent):
    name = "planner"
    description = "Turns the parsed brief into research questions, an outline and source needs"
    temperature = 0.4
    system_prompt = (
        "You help a student PLAN their own assignment. You never write the assignment "
        "itself: no paragraphs of essay text, only a plan.\n"
        "Produce: research questions; an outline whose sections each have a heading, a "
        "purpose, key points the student should develop, and a word budget; the kinds "
        "of sources the student must find; search queries for library databases.\n"
        "suggested_readings is optional. Only list works you are confident exist, give "
        "the full reference with its DOI, URL or ISBN when you know it, and never "
        "invent a reference. An empty list is better than a guess.\n"
        "Reply with ONE JSON object and nothing else, exactly this shape:\n"
        '{"working_title": "...", "research_questions": ["..."], '
        '"outline": [{"heading": "...", "purpose": "...", "key_points": ["..."], '
        '"words": 300}], '
        '"source_needs": [{"need": "...", "why": "...", "where_to_look": "..."}], '
        '"search_queries": ["..."], '
        '"suggested_readings": [{"reference": "full reference incl. DOI/URL/ISBN", '
        '"why": "..."}]}'
    )

    async def execute(
        self, brief: BriefInfo, brief_text: str, words: int | None, style: str, language: str
    ) -> PlanOutput:
        target = f"{words} words" if words else "not stated; propose a sensible length"
        prompt = (
            f"PARSED BRIEF:\n{brief.model_dump_json(indent=1)}\n\n"
            f"ORIGINAL BRIEF:\n{brief_text}\n\n"
            f"TARGET LENGTH: {target}. CITATION STYLE: {STYLE_GUIDE[style]}.\n"
            "Return the JSON object."
        )
        response = await self.ask(
            prompt, system=f"{self.system_prompt}\n{llm_instruction(language)}"
        )
        return parse_json(response.content, agent=self.name, schema=PlanOutput)


# --- feedback -----------------------------------------------------------------


class Comment(_Model):
    paragraph: int | None = None
    quote: Text = ""
    issue: Text = Field(min_length=1)
    suggestion: Text = ""
    severity: Literal["major", "minor"] = "minor"

    @field_validator("paragraph", mode="before")
    @classmethod
    def _para(cls, value: Any) -> int | None:
        digits = "".join(c for c in str(value or "") if c.isdigit())
        return int(digits) if digits else None

    @field_validator("severity", mode="before")
    @classmethod
    def _severity(cls, value: Any) -> str:
        text = _text(value).lower()
        return "major" if text in ("major", "high", "critical", "error", "important") else "minor"


class FeedbackOutput(_Model):
    """What every feedback agent must return. ``comments`` is required (may be empty)."""

    summary: Text = ""
    strengths: Texts = Field(default_factory=list)
    comments: list[Comment]


class FeedbackAgent(Agent):
    """Comments on one aspect of the student's draft. Never rewrites it."""

    focus: ClassVar[str] = ""
    temperature = 0.2

    @classmethod
    def build_system_prompt(cls, language: str) -> str:
        return (
            f"You are the {cls.name} reviewer giving feedback on a student's own draft. "
            f"Look only at: {cls.focus}\n"
            "You comment; you do NOT rewrite. Never return a rewritten paragraph. Each "
            "suggestion says what to change in at most two sentences; the student does "
            "the writing.\n"
            "Paragraphs are numbered [P1], [P2], ... Point to the paragraph number and "
            "copy a short exact quote (at most 15 words) from it.\n"
            "Reply with ONE JSON object and nothing else, exactly this shape:\n"
            '{"summary": "one or two sentences", "strengths": ["..."], "comments": ['
            '{"paragraph": 2, "quote": "exact words from the draft", "issue": "what is '
            'wrong and why", "suggestion": "what to change", "severity": "major|minor"}]}\n'
            "Use an empty comments list when you have nothing to report.\n"
            f"{llm_instruction(language)}"
        )

    async def execute(
        self, numbered_draft: str, language: str, brief_text: str = "", style: str = "apa"
    ) -> FeedbackOutput:
        parts = []
        if brief_text:
            parts.append(f"ASSIGNMENT BRIEF:\n{brief_text}")
        parts.append(f"EXPECTED CITATION STYLE: {STYLE_GUIDE[style]}")
        parts.append(f"STUDENT DRAFT:\n{numbered_draft}")
        parts.append("Return the JSON object.")
        response = await self.ask("\n\n".join(parts), system=self.build_system_prompt(language))
        return parse_json(response.content, agent=self.name, schema=FeedbackOutput)


class StructureAgent(FeedbackAgent):
    name = "structure"
    description = "Organisation: introduction, paragraph order, transitions, conclusion"
    focus = (
        "organisation: whether the introduction states a clear aim or thesis, whether "
        "paragraphs follow a logical order with one main idea each, transitions, and "
        "whether the conclusion answers the aim. Also whether the brief's required "
        "parts are present."
    )


class ArgumentAgent(FeedbackAgent):
    name = "argument"
    description = "Argument: claims, evidence, reasoning, counter-arguments"
    focus = (
        "argument: unsupported or overstated claims, gaps in reasoning, evidence that "
        "does not support the claim, missing counter-arguments, description where "
        "analysis is needed."
    )


class ClarityAgent(FeedbackAgent):
    name = "clarity"
    description = "Clarity and academic style of the student's own sentences"
    focus = (
        "clarity and academic style: unclear or overlong sentences, vague wording, "
        "informal register, grammar and spelling, inconsistent terms. Point to the "
        "problem; do not supply a rewritten sentence."
    )


class CitationReviewAgent(FeedbackAgent):
    name = "citations"
    description = "Where claims need a citation and whether citations follow the style"
    focus = (
        "citations: factual claims, statistics or other people's ideas that need a "
        "citation and have none; in-text citations that do not follow the expected "
        "style; reference list entries with missing details. Never propose a specific "
        "source to cite: say what kind of source is needed."
    )


FEEDBACK_AGENTS: dict[str, type[FeedbackAgent]] = {
    a.name: a for a in (StructureAgent, ArgumentAgent, ClarityAgent, CitationReviewAgent)
}


# --- cite ---------------------------------------------------------------------


class FormattedRef(_Model):
    index: int
    formatted: Reference = Field(min_length=1)
    missing: Texts = Field(default_factory=list)
    note: Text = ""


class CiteOutput(_Model):
    references: list[FormattedRef] = Field(min_length=1)


class FormatterAgent(Agent):
    name = "formatter"
    description = "Formats references the user supplied into one citation style"
    temperature = 0.0
    system_prompt = (
        "You format references that a student supplied into one citation style. Use "
        "ONLY the details in each input. Never add a reference, and never fill in a "
        "DOI, URL, ISBN, page range, volume, issue or publisher that the input does "
        "not contain: list what is missing instead. Do not number the entries. Mark "
        "italics with Markdown *asterisks*, never HTML.\n"
        "Reply with ONE JSON object and nothing else, exactly this shape:\n"
        '{"references": [{"index": 1, "formatted": "the formatted reference", '
        '"missing": ["what the style needs but the input lacks"], "note": ""}]}\n'
        "Return exactly one item per input reference, with the input's index."
    )

    async def execute(self, references: list[str], style: str, language: str) -> CiteOutput:
        listing = "\n".join(f"{i}. {ref}" for i, ref in enumerate(references, start=1))
        prompt = (
            f"CITATION STYLE: {STYLE_GUIDE[style]}\n\nREFERENCES SUPPLIED BY THE STUDENT:\n"
            f"{listing}\n\nReturn the JSON object."
        )
        response = await self.ask(
            prompt, system=f"{self.system_prompt}\n{llm_instruction(language)}"
        )
        return parse_json(response.content, agent=self.name, schema=CiteOutput)
