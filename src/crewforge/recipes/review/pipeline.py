"""Review pipeline: six reviewers in parallel, then one summary step.

Strict by default: if any reviewer fails (error, empty or unparseable reply)
the run raises :class:`CrewFailedError` naming every failed agent. With
``allow_partial=True`` the run continues as long as at least one reviewer
succeeded; the failed agents are kept in :attr:`ReviewResult.agent_results`
with ``status="failed"`` so the report can show them.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import httpx

from ...core.client import LLMClient
from ...core.config import LLMConfig
from ...core.crew import Crew
from ...core.usage import UsageTracker
from .agents import REVIEW_AGENTS, AgentResult, get_agent

logger = logging.getLogger(__name__)


@dataclass
class ReviewResult:
    status: str = "success"  # success | partial
    code: str = ""
    language: str = ""
    agent_results: dict[str, AgentResult] = field(default_factory=dict)
    summary_result: AgentResult | None = None
    total_tokens: int = 0
    duration_s: float = 0.0
    usage: dict = field(default_factory=dict)
    tracker: UsageTracker | None = field(default=None, repr=False)

    @property
    def ok(self) -> bool:
        return self.status in ("success", "partial")

    @property
    def failed_agents(self) -> list[str]:
        return [name for name, r in self.agent_results.items() if not r.ok]

    @property
    def total_findings(self) -> int:
        return sum(r.finding_count for r in self.agent_results.values())


def findings_context(results: dict[str, AgentResult]) -> str:
    """Compact JSON digest of every successful reviewer, fed to the summary agent."""
    blocks = []
    for name, r in results.items():
        if not r.ok:
            continue
        payload = {"summary": r.summary, "findings": r.findings}
        blocks.append(f"=== {name.upper()} ===\n{json.dumps(payload, ensure_ascii=False)}")
    return "\n\n".join(blocks)


class CodeReviewCrew:
    """Coordinates the review agents on one shared client and usage tracker."""

    def __init__(
        self,
        config: LLMConfig,
        *,
        agents: list[str] | None = None,
        allow_partial: bool = False,
        client: LLMClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        self.agents = list(agents) if agents else list(REVIEW_AGENTS)
        unknown = [a for a in self.agents if a not in REVIEW_AGENTS]
        if unknown:
            raise ValueError(f"unknown reviewer(s): {', '.join(unknown)}; known: {REVIEW_AGENTS}")
        self.allow_partial = allow_partial
        self._client = client
        self._transport = transport
        self.crew: Crew | None = None

    async def review(self, code: str, language: str = "") -> ReviewResult:
        result = ReviewResult(code=code, language=language)
        crew = Crew("review", self.config, client=self._client, transport=self._transport)
        self.crew = crew
        async with crew:
            work = {
                name: get_agent(name, client=crew.client, tracker=crew.tracker).execute(
                    code=code, language=language
                )
                for name in self.agents
            }
            logger.info("[review] running %d reviewers in parallel", len(work))
            done = await crew.parallel(work, require="any" if self.allow_partial else "all")
            for name in self.agents:
                if name in done:
                    result.agent_results[name] = done[name]
            for failure in crew.failures:
                result.agent_results[failure.agent] = AgentResult(
                    agent_name=failure.agent,
                    status="failed",
                    error=failure.error,
                    kind=failure.kind,
                )
            # keep the configured agent order in reports
            result.agent_results = {
                n: result.agent_results[n] for n in self.agents if n in result.agent_results
            }

            summary = get_agent("summary", client=crew.client, tracker=crew.tracker)
            result.summary_result = await crew.step(
                summary,
                summary.execute(
                    code=code, language=language, context=findings_context(result.agent_results)
                ),
            )
        result.status = "partial" if crew.failures else "success"
        result.total_tokens = crew.tracker.total_tokens
        result.duration_s = crew.tracker.duration_s
        result.usage = crew.tracker.summary()
        result.tracker = crew.tracker
        return result
