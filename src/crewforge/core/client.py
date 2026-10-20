"""One async client for every OpenAI-compatible ``/chat/completions`` endpoint.

Policy, in one place:

* Non-streaming: ``"stream": false`` is always sent. Some compatible servers
  stream when the flag is omitted, which used to make every agent parse an
  SSE body as nothing and "succeed" with empty output.
* Retries: only HTTP 429, HTTP 5xx and network/timeout errors are retried,
  with bounded exponential backoff (``Retry-After`` honoured up to
  ``max_retry_delay``). 401/403 and every other 4xx fail on the first attempt.
* Usage: token counts come only from the provider's ``usage`` object. When a
  provider omits it, :attr:`Usage.reported` is ``False`` and the counts stay
  zero; nothing is estimated.
* Secrets: the key lives in request headers only. It is never logged and never
  part of an error message.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx

from .config import LLMConfig
from .errors import LLMError, LLMHTTPError, LLMResponseError

logger = logging.getLogger(__name__)


@dataclass
class Message:
    role: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class Usage:
    """Token usage exactly as the provider reported it."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0
    reported: bool = False  # False = provider sent no usage object

    @classmethod
    def from_payload(cls, data: Any) -> Usage:
        if not isinstance(data, dict):
            return cls()
        prompt = _as_int(data.get("prompt_tokens"))
        completion = _as_int(data.get("completion_tokens"))
        total = _as_int(data.get("total_tokens")) or prompt + completion
        details = data.get("prompt_tokens_details") or {}
        cached = _as_int(details.get("cached_tokens")) if isinstance(details, dict) else 0
        return cls(prompt, completion, total, cached, reported=True)

    def add(self, other: Usage) -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.total_tokens += other.total_tokens
        self.cached_tokens += other.cached_tokens
        self.reported = self.reported or other.reported


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


@dataclass
class ChatResponse:
    content: str
    usage: Usage = field(default_factory=Usage)
    model: str = ""
    finish_reason: str = ""
    reasoning: str = ""
    latency_ms: float = 0.0
    attempts: int = 1


MessageLike = Message | dict[str, str]


def is_retryable_status(status: int) -> bool:
    """429 and 5xx are transient; every other status is a caller/config problem."""
    return status == 429 or status >= 500


class LLMClient:
    """Async OpenAI-compatible chat client with a strict retry policy.

    Use as an async context manager, or call :meth:`aclose` when done. A
    ``transport`` can be injected (``httpx.MockTransport``) for tests.
    """

    def __init__(
        self,
        config: LLMConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.config = config
        self._transport = transport
        self._sleep = sleep
        self._http: httpx.AsyncClient | None = None
        self.total_usage = Usage()
        self.request_count = 0

    async def __aenter__(self) -> LLMClient:
        self._ensure_http()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    def _ensure_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                base_url=self.config.base_url,
                headers=self.config.headers,
                timeout=httpx.Timeout(self.config.timeout),
                transport=self._transport,
            )
        return self._http

    async def aclose(self) -> None:
        if self._http is not None and not self._http.is_closed:
            await self._http.aclose()

    def _backoff(self, attempt: int, response: httpx.Response | None) -> float:
        delay = self.config.retry_delay * (2 ** (attempt - 1))
        if response is not None:
            retry_after = response.headers.get("retry-after", "")
            try:
                delay = max(delay, float(retry_after))
            except ValueError:
                pass
        return min(delay, self.config.max_retry_delay)

    async def chat(
        self,
        messages: Sequence[MessageLike],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> ChatResponse:
        payload: dict[str, Any] = {
            "model": model or self.config.model,
            "messages": [m.to_dict() if isinstance(m, Message) else dict(m) for m in messages],
            # ``is not None``: an explicit temperature of 0 must be sent as 0.
            "temperature": self.config.temperature if temperature is None else temperature,
            "max_tokens": self.config.max_tokens if max_tokens is None else max_tokens,
            "stream": False,
        }
        if extra:
            payload.update(extra)
            payload["stream"] = False

        http = self._ensure_http()
        attempts = max(1, self.config.max_retries)
        start = time.monotonic()
        last_exc: Exception | None = None
        for attempt in range(1, attempts + 1):
            response: httpx.Response | None = None
            try:
                response = await http.post("/chat/completions", json=payload)
            except httpx.TransportError as exc:  # connect/read errors and timeouts
                last_exc = exc
                if attempt < attempts:
                    logger.warning("LLM request failed (%s); retry %d", type(exc).__name__, attempt)
                    await self._sleep(self._backoff(attempt, None))
                    continue
                raise LLMError(
                    f"cannot reach {self.config.base_url} after {attempt} attempt(s): "
                    f"{type(exc).__name__}: {exc}"
                ) from exc

            if response.status_code >= 400:
                if is_retryable_status(response.status_code) and attempt < attempts:
                    logger.warning("LLM HTTP %s; retry %d", response.status_code, attempt)
                    await self._sleep(self._backoff(attempt, response))
                    continue
                raise LLMHTTPError(
                    response.status_code,
                    self._http_error_message(response, attempt),
                    attempts=attempt,
                )
            return self._parse(response, start, attempt)
        raise LLMError(f"request failed: {last_exc}")  # pragma: no cover - loop always returns

    def _http_error_message(self, response: httpx.Response, attempts: int) -> str:
        detail = ""
        try:
            body = response.json()
            err = body.get("error") if isinstance(body, dict) else None
            if isinstance(err, dict):
                detail = str(err.get("message") or err.get("code") or "")
            elif err:
                detail = str(err)
            elif isinstance(body, dict):
                detail = str(body.get("message") or body.get("detail") or "")
        except ValueError:
            detail = response.text
        detail = " ".join(detail.split())[:300]
        msg = f"HTTP {response.status_code} from {self.config.base_url}"
        if response.status_code in (401, 403):
            msg += f" (authentication failed — check {self.config.key_env_var})"
        elif response.status_code == 404:
            msg += f" (check the base URL and that model '{self.config.model}' exists)"
        if attempts > 1:
            msg += f" after {attempts} attempts"
        if detail:
            msg += f": {detail}"
        return msg

    def _parse(self, response: httpx.Response, start: float, attempts: int) -> ChatResponse:
        try:
            data = response.json()
        except ValueError as exc:
            snippet = " ".join(response.text.split())[:120]
            raise LLMResponseError(
                f"endpoint returned non-JSON body (is it streaming?): {snippet!r}"
            ) from exc
        choices = data.get("choices") if isinstance(data, dict) else None
        if not choices or not isinstance(choices, list) or not isinstance(choices[0], dict):
            raise LLMResponseError(f"response has no choices: {str(data)[:160]!r}")
        choice = choices[0]
        message = choice.get("message") or {}
        usage = Usage.from_payload(data.get("usage"))
        self.total_usage.add(usage)
        self.request_count += 1
        return ChatResponse(
            content=message.get("content") or "",
            usage=usage,
            model=data.get("model") or "",
            finish_reason=choice.get("finish_reason") or "",
            reasoning=message.get("reasoning_content") or message.get("reasoning") or "",
            latency_ms=round((time.monotonic() - start) * 1000, 1),
            attempts=attempts,
        )
