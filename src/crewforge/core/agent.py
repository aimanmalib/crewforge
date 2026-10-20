"""The :class:`Agent` base class: one role, one system prompt, one LLM call at a time."""

from __future__ import annotations

import time
from typing import Any, ClassVar

from .client import ChatResponse, LLMClient, Message
from .errors import EmptyOutputError
from .parsing import M, parse_json
from .usage import UsageTracker


class Agent:
    """Base class for every agent in every recipe.

    Subclasses set :attr:`name`, :attr:`description` and :attr:`system_prompt`
    and implement their task with :meth:`ask` / :meth:`ask_json`. Both record
    provider-reported usage and refuse to return empty or unparseable output:
    that refusal is what lets a crew fail honestly instead of reporting success.
    """

    name: ClassVar[str] = "agent"
    description: ClassVar[str] = ""
    system_prompt: ClassVar[str] = "You are a precise, factual assistant."
    #: Per-agent sampling defaults; ``None`` means "use the LLMConfig value".
    temperature: ClassVar[float | None] = None
    max_tokens: ClassVar[int | None] = None

    def __init__(
        self,
        client: LLMClient,
        tracker: UsageTracker | None = None,
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self.client = client
        self.tracker = tracker if tracker is not None else UsageTracker()
        self._system_prompt = system_prompt
        self._model = model
        self._temperature = temperature if temperature is not None else self.temperature
        self._max_tokens = max_tokens if max_tokens is not None else self.max_tokens

    @property
    def effective_system_prompt(self) -> str:
        return self._system_prompt or self.system_prompt

    def build_messages(
        self, prompt: str, *, system: str | None = None, context: str | None = None
    ) -> list[Message]:
        messages = [Message("system", system or self.effective_system_prompt)]
        if context:
            messages.append(Message("user", f"Context:\n{context}"))
        messages.append(Message("user", prompt))
        return messages

    async def ask(
        self,
        prompt: str,
        *,
        system: str | None = None,
        context: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        allow_empty: bool = False,
    ) -> ChatResponse:
        """Send one prompt; return the response or raise naming this agent."""
        messages = self.build_messages(prompt, system=system, context=context)
        start = time.monotonic()
        try:
            response = await self.client.chat(
                messages,
                model=self._model,
                temperature=temperature if temperature is not None else self._temperature,
                max_tokens=max_tokens if max_tokens is not None else self._max_tokens,
            )
        except Exception:
            self.tracker.record(self.name, None, (time.monotonic() - start) * 1000, error=True)
            raise
        self.tracker.record(
            self.name,
            response.usage,
            (time.monotonic() - start) * 1000,
            retries=max(0, response.attempts - 1),
        )
        # Honest-failure guard: a blank completion is a failure of this agent,
        # never an answer. Removing this check makes tests/core/test_honest_failure.py red.
        if not allow_empty and not response.content.strip():
            detail = f"finish_reason={response.finish_reason}" if response.finish_reason else ""
            raise EmptyOutputError(self.name, detail)
        return response

    async def ask_json(
        self,
        prompt: str,
        *,
        schema: type[M] | None = None,
        expect: type | tuple[type, ...] = dict,
        system: str | None = None,
        context: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Any:
        """Like :meth:`ask` but the reply must parse as JSON (and match ``schema``)."""
        response = await self.ask(
            prompt,
            system=system,
            context=context,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return parse_json(response.content, agent=self.name, expect=expect, schema=schema)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self.name!r}>"
