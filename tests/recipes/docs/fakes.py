"""Helpers for the docs recipe tests (ported from documind)."""

from __future__ import annotations

from crewforge.core.client import ChatResponse, Usage


def completion(
    content: str = "Test response",
    reasoning_content: str = "",
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
    total_tokens: int | None = None,
    **_: object,
) -> ChatResponse:
    """documind's ``CompletionResponse(...)`` as a crewforge ``ChatResponse``."""
    total = prompt_tokens + completion_tokens if total_tokens is None else total_tokens
    return ChatResponse(
        content=content,
        reasoning=reasoning_content,
        usage=Usage(prompt_tokens, completion_tokens, total, reported=True),
        model="test-model",
        finish_reason="stop",
        latency_ms=250.0,
    )
