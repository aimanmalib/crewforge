"""Exception hierarchy.

Every failure a user can hit maps to one of these, and every agent-level
failure carries the agent's name so the CLI can say exactly *who* failed.
"""

from __future__ import annotations

from dataclasses import dataclass


class CrewForgeError(Exception):
    """Base class for all crewforge errors."""


class ConfigError(CrewForgeError):
    """The configuration cannot work (unknown provider, missing key or URL, ...)."""


class LLMError(CrewForgeError):
    """The LLM endpoint could not produce a usable response."""


class LLMHTTPError(LLMError):
    """The endpoint answered with a non-2xx status after any allowed retries."""

    def __init__(self, status_code: int, message: str, *, attempts: int = 1) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.attempts = attempts


class LLMResponseError(LLMError):
    """The endpoint answered 2xx but the body is not a chat completion."""


class AgentError(CrewForgeError):
    """An agent produced output that cannot be used. Always names the agent."""

    def __init__(self, agent: str, reason: str) -> None:
        super().__init__(f"agent '{agent}' {reason}")
        self.agent = agent
        self.reason = reason


class EmptyOutputError(AgentError):
    """The model returned no content (blank, whitespace or null)."""

    def __init__(self, agent: str, detail: str = "") -> None:
        reason = "returned empty output"
        if detail:
            reason += f" ({detail})"
        super().__init__(agent, reason)


class OutputParseError(AgentError):
    """The model returned content, but not in the structure the agent requires."""

    def __init__(self, agent: str, detail: str, excerpt: str = "") -> None:
        reason = f"returned unparseable output: {detail}"
        if excerpt:
            reason += f" — got: {excerpt!r}"
        super().__init__(agent, reason)
        self.excerpt = excerpt


@dataclass(frozen=True)
class AgentFailure:
    """One agent that failed inside a crew run."""

    agent: str
    error: str
    kind: str = "error"  # empty | parse | http | error

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.agent}: {self.error}"


class CrewFailedError(CrewForgeError):
    """A crew run cannot honestly report success.

    Raised when a required agent failed, returned nothing, or returned output
    that could not be parsed. ``failures`` names every agent involved.
    """

    def __init__(self, crew: str, failures: list[AgentFailure]) -> None:
        self.crew = crew
        self.failures = list(failures)
        names = ", ".join(f"'{f.agent}'" for f in self.failures) or "(none)"
        detail = "; ".join(f"{f.agent}: {f.error}" for f in self.failures)
        super().__init__(f"{crew} failed — agent(s) {names}: {detail}")

    @property
    def agents(self) -> list[str]:
        return [f.agent for f in self.failures]


def classify(exc: BaseException) -> str:
    """Short machine-readable kind for an exception (used in reports/JSON)."""
    if isinstance(exc, EmptyOutputError):
        return "empty"
    if isinstance(exc, OutputParseError):
        return "parse"
    if isinstance(exc, LLMHTTPError):
        return "http"
    return "error"
