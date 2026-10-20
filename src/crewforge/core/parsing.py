"""Structured-output parsing for LLM replies.

Real models wrap JSON in Markdown fences, add a sentence before it, or answer
with prose. :func:`extract_json` tolerates the first two; :func:`parse_json`
turns the third into an :class:`OutputParseError` that names the agent instead
of letting a default value slip through as if it were an answer.
"""

from __future__ import annotations

import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .errors import EmptyOutputError, OutputParseError

_FENCE = re.compile(r"```[ \t]*([A-Za-z0-9_+-]*)[ \t]*\n?(.*?)```", re.DOTALL)

M = TypeVar("M", bound=BaseModel)

_MISSING = object()


def extract_json(text: str | None) -> Any:
    """Best-effort JSON extraction. Returns ``None`` when nothing parses.

    Tries, in order: the whole reply, each fenced code block, the outermost
    ``{...}`` span, then the outermost ``[...]`` span.
    """
    value = _extract(text)
    return None if value is _MISSING else value


def _extract(text: str | None) -> Any:
    if not text or not text.strip():
        return _MISSING
    candidates = [text.strip()]
    candidates += [m.group(2).strip() for m in _FENCE.finditer(text)]
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start, end = text.find(open_ch), text.rfind(close_ch)
        if start != -1 and end > start:
            candidates.append(text[start : end + 1])
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
    return _MISSING


def _excerpt(text: str, limit: int = 120) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def parse_json(
    text: str | None,
    *,
    agent: str,
    expect: type | tuple[type, ...] = dict,
    schema: type[M] | None = None,
) -> Any:
    """Parse an agent's reply as JSON or raise an error naming the agent.

    ``expect`` is the required top-level type (``dict`` by default). With
    ``schema`` (a pydantic model) the object is validated and the model
    instance is returned.
    """
    if not text or not text.strip():
        raise EmptyOutputError(agent)
    value = _extract(text)
    if value is _MISSING:
        raise OutputParseError(agent, "no JSON found", _excerpt(text))
    if not isinstance(value, expect):
        want = (
            " or ".join(t.__name__ for t in expect)
            if isinstance(expect, tuple)
            else expect.__name__
        )
        raise OutputParseError(
            agent, f"expected a JSON {want}, got {type(value).__name__}", _excerpt(text)
        )
    if schema is not None:
        try:
            return schema.model_validate(value)
        except ValidationError as exc:
            first = exc.errors()[0]
            loc = ".".join(str(p) for p in first.get("loc", ())) or "(root)"
            raise OutputParseError(
                agent, f"JSON does not match {schema.__name__}: {loc}: {first.get('msg')}"
            ) from exc
    return value


def extract_code_block(text: str | None, language: str = "") -> str | None:
    """Return the first fenced code block (preferring ``language``), else ``None``."""
    if not text:
        return None
    blocks = [(m.group(1).lower(), m.group(2)) for m in _FENCE.finditer(text)]
    if not blocks:
        return None
    if language:
        for lang, body in blocks:
            if lang == language.lower():
                return body.strip("\n")
    return blocks[0][1].strip("\n")
