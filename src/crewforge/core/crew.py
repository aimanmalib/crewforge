"""A :class:`Crew` runs agents in sequential steps and parallel stages.

The crew owns the shared client and usage tracker, and it is where honest
failure is enforced for a whole run: a step whose agent raised, returned
nothing, or returned unparseable output stops the run with
:class:`CrewFailedError` naming the agent(s). Recipes never decide on their own
that a half-empty run is a success.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Mapping
from typing import Any, Literal, TypeVar

import httpx

from .agent import Agent
from .client import LLMClient
from .config import LLMConfig
from .errors import AgentFailure, ConfigError, CrewFailedError, EmptyOutputError, classify
from .usage import UsageTracker

logger = logging.getLogger(__name__)

T = TypeVar("T")
A = TypeVar("A", bound=Agent)


def is_empty(value: Any) -> bool:
    """``None``, blank strings and empty containers count as "returned nothing"."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict, set, frozenset)):
        return len(value) == 0
    return False


class Crew:
    """Shared client + tracker + failure bookkeeping for one run of a recipe."""

    def __init__(
        self,
        name: str,
        config: LLMConfig,
        *,
        client: LLMClient | None = None,
        tracker: UsageTracker | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        validate: bool = True,
    ) -> None:
        if validate and client is None:
            config.require_valid()
        self.name = name
        self.config = config
        self._owns_client = client is None
        self.client = client if client is not None else LLMClient(config, transport=transport)
        self.tracker = tracker if tracker is not None else UsageTracker()
        self.failures: list[AgentFailure] = []

    async def __aenter__(self) -> Crew:
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.tracker.finish()
        if self._owns_client:
            await self.client.aclose()

    def agent(self, cls: type[A], **kwargs: Any) -> A:
        """Instantiate an agent bound to this crew's client and tracker."""
        return cls(self.client, self.tracker, **kwargs)

    def _fail(self, agent: str, exc: BaseException) -> AgentFailure:
        failure = AgentFailure(
            agent=agent, error=str(exc) or type(exc).__name__, kind=classify(exc)
        )
        self.failures.append(failure)
        logger.info("[%s] agent %r failed: %s", self.name, agent, failure.error)
        return failure

    @staticmethod
    def _checked(agent: str, value: T, allow_empty: bool) -> T:
        # Second honest-failure guard: even if an agent's own code swallowed an
        # error and returned a default, "nothing" is never a successful result.
        if not allow_empty and is_empty(value):
            raise EmptyOutputError(agent, "result was empty")
        return value

    async def step(self, agent: str | Agent, work: Awaitable[T], *, allow_empty: bool = False) -> T:
        """Run one required step; raise :class:`CrewFailedError` if it fails."""
        name = agent.name if isinstance(agent, Agent) else agent
        try:
            return self._checked(name, await work, allow_empty)
        except ConfigError:
            raise
        except Exception as exc:
            raise CrewFailedError(self.name, [self._fail(name, exc)]) from exc

    async def parallel(
        self,
        work: Mapping[str, Awaitable[Any]],
        *,
        require: Literal["all", "any"] = "all",
        allow_empty: bool = False,
    ) -> dict[str, Any]:
        """Run several agents concurrently.

        ``require="all"`` (default): any failure fails the run, naming every
        failed agent. ``require="any"``: failures are recorded in
        :attr:`failures` and the successful results are returned, unless none
        succeeded.
        """
        names = list(work)
        outcomes = await asyncio.gather(*work.values(), return_exceptions=True)
        results: dict[str, Any] = {}
        failed: list[AgentFailure] = []
        for name, outcome in zip(names, outcomes, strict=True):
            if isinstance(outcome, ConfigError):
                raise outcome
            if isinstance(outcome, BaseException):
                if not isinstance(outcome, Exception):
                    raise outcome  # CancelledError, KeyboardInterrupt: never swallow
                failed.append(self._fail(name, outcome))
                continue
            try:
                results[name] = self._checked(name, outcome, allow_empty)
            except EmptyOutputError as exc:
                failed.append(self._fail(name, exc))
        if failed and (require == "all" or not results):
            raise CrewFailedError(self.name, failed)
        return results

    def report(self) -> dict[str, Any]:
        return {
            "crew": self.name,
            "status": "partial" if self.failures else "success",
            "failures": [
                {"agent": f.agent, "kind": f.kind, "error": f.error} for f in self.failures
            ],
            "usage": self.tracker.summary(),
        }
