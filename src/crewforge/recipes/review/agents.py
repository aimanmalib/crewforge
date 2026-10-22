"""The review crew: six specialist reviewers plus a summary agent.

Every reviewer must answer with a JSON object holding a ``findings`` list
(possibly empty — clean code is a valid result). A reply that is empty, prose,
or the wrong shape is a failure of that agent, never "no findings".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...core.agent import Agent
from ...core.parsing import parse_json

SEVERITIES = ("critical", "error", "warning", "info")

# Words models commonly use instead of the four severities we accept.
_SEVERITY_ALIASES = {
    "high": "error",
    "major": "error",
    "blocker": "critical",
    "severe": "critical",
    "medium": "warning",
    "moderate": "warning",
    "minor": "info",
    "low": "info",
    "note": "info",
    "suggestion": "info",
    "style": "info",
}


class Finding(BaseModel):
    """One issue reported by a reviewer. Unknown extra keys are ignored."""

    model_config = ConfigDict(extra="ignore")

    severity: Literal["critical", "error", "warning", "info"] = "info"
    title: str = ""
    description: str = ""
    line: int | str | None = None
    suggestion: str = ""
    category: str = ""
    cwe: str | None = None

    @field_validator("severity", mode="before")
    @classmethod
    def _normalise_severity(cls, value: Any) -> str:
        text = str(value or "info").strip().lower()
        text = _SEVERITY_ALIASES.get(text, text)
        if text not in SEVERITIES:
            raise ValueError(f"severity must be one of {', '.join(SEVERITIES)}, not {value!r}")
        return text

    @field_validator("title", "description", "suggestion", "category", mode="before")
    @classmethod
    def _stringify(cls, value: Any) -> str:
        return "" if value is None else str(value)

    @field_validator("cwe", mode="before")
    @classmethod
    def _cwe_str(cls, value: Any) -> str | None:
        return None if value in (None, "") else str(value)


class ReviewOutput(BaseModel):
    """What every reviewer must return. ``findings`` is required (may be empty)."""

    model_config = ConfigDict(extra="ignore")

    findings: list[Finding]
    summary: str = ""

    @field_validator("summary", mode="before")
    @classmethod
    def _summary_str(cls, value: Any) -> str:
        return "" if value is None else str(value)


class SummaryOutput(BaseModel):
    """What the summary agent must return."""

    model_config = ConfigDict(extra="ignore")

    decision: Literal["APPROVE", "REQUEST_CHANGES", "COMMENT"]
    quality_score: int = Field(ge=0, le=100)
    top_issues: list[str] = Field(default_factory=list)
    summary: str = ""

    @field_validator("decision", mode="before")
    @classmethod
    def _decision_upper(cls, value: Any) -> str:
        return str(value or "").strip().upper().replace(" ", "_")

    @field_validator("top_issues", mode="before")
    @classmethod
    def _issues_as_text(cls, value: Any) -> list[str]:
        if not value:
            return []
        if not isinstance(value, list):
            value = [value]
        out = []
        for item in value:
            if isinstance(item, dict):
                item = item.get("title") or item.get("issue") or item.get("description") or item
            out.append(str(item))
        return out

    @field_validator("summary", mode="before")
    @classmethod
    def _summary_str(cls, value: Any) -> str:
        return "" if value is None else str(value)


@dataclass
class AgentResult:
    """One agent's contribution to a review (also used for failed agents)."""

    agent_name: str
    status: str = "success"  # success | failed
    findings: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    tokens_used: int = 0
    latency_ms: float = 0.0
    error: str | None = None
    kind: str | None = None  # failure kind: empty | parse | http | error
    reasoning: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "success"

    @property
    def finding_count(self) -> int:
        return len(self.findings)

    def _count(self, severity: str) -> int:
        return sum(1 for f in self.findings if f.get("severity") == severity)

    @property
    def critical_count(self) -> int:
        return self._count("critical")

    @property
    def error_count(self) -> int:
        return self._count("error")

    @property
    def warning_count(self) -> int:
        return self._count("warning")


_JSON_CONTRACT = """
Reply with ONE JSON object and nothing else, exactly this shape:
{"summary": "one or two sentences", "findings": [
  {"severity": "critical|error|warning|info", "title": "short title",
   "description": "what is wrong and why", "line": 12, "suggestion": "how to fix",
   "category": "short category", "cwe": "CWE-89 or null"}
]}
Use an empty "findings" list when you find nothing in your area."""


class ReviewerAgent(Agent):
    """A reviewer that inspects code for one concern and returns findings."""

    focus: ClassVar[str] = "general quality"
    checklist: ClassVar[str] = ""

    @classmethod
    def build_system_prompt(cls) -> str:
        return (
            f"You are the {cls.name} reviewer in a code review crew.\n"
            f"Look for: {cls.checklist}\n"
            "Report only real, specific problems in the code you are given; cite line "
            "numbers when you can." + _JSON_CONTRACT
        )

    def build_prompt(self, code: str, language: str = "", context: str = "") -> str:
        parts = [f"Review the following {language or 'code'} for {self.focus}."]
        if context:
            parts.append(f"Context: {context}")
        parts.append(f"CODE:\n```\n{code}\n```")
        parts.append("Return the JSON object described in your instructions.")
        return "\n\n".join(parts)

    async def execute(self, code: str, language: str = "", context: str = "") -> AgentResult:
        """Run the review; raises (naming this agent) on empty or unparseable output."""
        response = await self.ask(
            self.build_prompt(code, language, context), system=self.build_system_prompt()
        )
        parsed = parse_json(response.content, agent=self.name, schema=ReviewOutput)
        return AgentResult(
            agent_name=self.name,
            findings=[f.model_dump() for f in parsed.findings],
            summary=parsed.summary,
            tokens_used=response.usage.total_tokens,
            latency_ms=response.latency_ms,
            reasoning=response.reasoning or None,
        )


class SecurityAgent(ReviewerAgent):
    name = "security"
    description = "Identifies security vulnerabilities, injection risks, and unsafe patterns"
    focus = "security vulnerabilities"
    checklist = (
        "SQL injection, XSS, CSRF, hardcoded secrets, insecure crypto, path traversal, "
        "unsafe deserialization, missing input validation, insecure dependencies. "
        "Include the CWE id when one applies."
    )


class StyleAgent(ReviewerAgent):
    name = "style"
    description = "Checks naming conventions, formatting, and language idioms"
    focus = "style and conventions"
    checklist = (
        "naming conventions, overly long functions (>50 lines), unused imports, magic "
        "numbers, dead code, non-idiomatic constructs, inconsistent formatting."
    )


class ComplexityAgent(ReviewerAgent):
    name = "complexity"
    description = "Measures cyclomatic complexity and suggests refactoring"
    focus = "complexity"
    checklist = (
        "high cyclomatic/cognitive complexity (warn >10, error >20 per function), "
        "duplication, long parameter lists (>4), god classes, deep nesting, "
        "refactoring opportunities."
    )


class LogicAgent(ReviewerAgent):
    name = "logic"
    description = "Detects logical errors, edge cases, and potential bugs"
    focus = "logical errors and edge cases"
    checklist = (
        "off-by-one errors, None/null handling, unhandled exceptions, overflow, float "
        "comparison, boundary checks, boolean logic, state bugs, race conditions, "
        "resource leaks."
    )


class TestingAgent(ReviewerAgent):
    __test__ = False  # not a pytest test class despite the name

    name = "testing"
    description = "Evaluates test coverage and suggests missing test cases"
    focus = "test coverage"
    checklist = (
        "untested functions and branches, missing edge-case and error-path tests, weak "
        "assertions, boundary values. Put a short suggested test in 'suggestion'."
    )


class DocumentationAgent(ReviewerAgent):
    name = "documentation"
    description = "Checks docstrings, comments, and documentation completeness"
    focus = "documentation quality"
    checklist = (
        "missing or outdated docstrings, undocumented parameters, missing type hints, "
        "stale comments, TODO/FIXME/HACK markers."
    )


class SummaryAgent(Agent):
    """Aggregates the reviewers' findings into one decision."""

    name = "summary"
    description = "Aggregates findings into a prioritized review report"
    system_prompt = (
        "You are the summary agent of a code review crew. You receive the findings of "
        "several specialist reviewers. Deduplicate them, prioritise by severity, and decide.\n"
        "Reply with ONE JSON object and nothing else, exactly this shape:\n"
        '{"decision": "APPROVE|REQUEST_CHANGES|COMMENT", "quality_score": 0-100, '
        '"top_issues": ["most important issue first", "..."], '
        '"summary": "two to four sentences for the author"}'
    )

    def build_prompt(self, code: str, language: str = "", context: str = "") -> str:
        return (
            f"Summarise this review of {language or 'code'}.\n\n"
            f"REVIEWER FINDINGS:\n{context or '(no findings were reported)'}\n\n"
            f"CODE UNDER REVIEW:\n```\n{code}\n```\n\n"
            "Return the JSON object described in your instructions."
        )

    async def execute(self, code: str, language: str = "", context: str = "") -> AgentResult:
        response = await self.ask(self.build_prompt(code, language, context))
        parsed = parse_json(response.content, agent=self.name, schema=SummaryOutput)
        return AgentResult(
            agent_name=self.name,
            summary=parsed.summary,
            tokens_used=response.usage.total_tokens,
            latency_ms=response.latency_ms,
            reasoning=response.reasoning or None,
            data=parsed.model_dump(),
        )


REVIEW_AGENTS: list[str] = [
    "security",
    "style",
    "complexity",
    "logic",
    "testing",
    "documentation",
]

AGENT_REGISTRY: dict[str, type[ReviewerAgent] | type[SummaryAgent]] = {
    "security": SecurityAgent,
    "style": StyleAgent,
    "complexity": ComplexityAgent,
    "logic": LogicAgent,
    "testing": TestingAgent,
    "documentation": DocumentationAgent,
    "summary": SummaryAgent,
}


def get_agent(name: str, **kwargs: Any) -> ReviewerAgent | SummaryAgent:
    """Instantiate a review agent by name (``client=``, ``tracker=`` keyword args)."""
    cls = AGENT_REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown agent: {name}. Available: {list(AGENT_REGISTRY)}")
    return cls(**kwargs)
