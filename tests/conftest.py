"""Shared fixtures: hermetic env + a fake OpenAI-compatible endpoint.

``fake_llm`` routes the *real* :class:`LLMClient` through ``httpx.MockTransport``,
so tests exercise payload building, response parsing, usage accounting and the
honest-failure guards exactly as a live run would — only the network is fake.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from crewforge.core.client import LLMClient
from crewforge.core.config import LLMConfig
from crewforge.core.providers import ENV_API_KEY, ENV_BASE_URL, ENV_MODEL, ENV_PROVIDER, PROVIDERS


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch):
    """Ignore provider settings from the developer's shell (keys, URLs, models)."""
    names = {ENV_PROVIDER, ENV_API_KEY, ENV_BASE_URL, ENV_MODEL}
    for p in PROVIDERS.values():
        names |= {p.env_key, p.env_base}
    for name in names:
        monkeypatch.delenv(name, raising=False)


Reply = str | dict | httpx.Response | None


class FakeLLM:
    """Scripted OpenAI-compatible endpoint.

    * ``replies``: list of contents returned in order (the last one repeats).
    * ``responder``: ``fn(payload) -> str | dict | httpx.Response`` for routing
      by prompt; overrides ``replies``.
    * ``usage``: usage object to attach (``None`` = provider reports no usage).
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.replies: list[Reply] = ["ok"]
        self.responder: Callable[[dict[str, Any]], Reply] | None = None
        self.usage: dict[str, int] | None = {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        }
        self.sleeps: list[float] = []

    def system_prompt(self, i: int) -> str:
        return self.calls[i]["messages"][0]["content"]

    def user_prompt(self, i: int) -> str:
        return self.calls[i]["messages"][-1]["content"]

    def handler(self, request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        self.calls.append(payload)
        if self.responder is not None:
            reply = self.responder(payload)
        else:
            reply = self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]
        if isinstance(reply, httpx.Response):
            return reply
        body: dict[str, Any] = (
            reply
            if isinstance(reply, dict)
            else {
                "model": payload.get("model", "fake"),
                "choices": [{"message": {"content": reply}, "finish_reason": "stop"}],
            }
        )
        if self.usage is not None and "usage" not in body:
            body = {**body, "usage": dict(self.usage)}
        return httpx.Response(200, json=body)

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)

    def client(self, config: LLMConfig | None = None) -> LLMClient:
        cfg = config or LLMConfig(provider="openai", api_key="sk-test")
        return LLMClient(cfg, transport=httpx.MockTransport(self.handler), sleep=self.sleep)


@pytest.fixture
def fake_llm(monkeypatch) -> FakeLLM:
    """Every LLMClient created during the test talks to this fake endpoint."""
    fake = FakeLLM()
    original_init = LLMClient.__init__

    def patched_init(self, config, *, transport=None, sleep=None):
        original_init(
            self,
            config,
            transport=transport or httpx.MockTransport(fake.handler),
            sleep=sleep or fake.sleep,
        )

    monkeypatch.setattr(LLMClient, "__init__", patched_init)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    return fake


@pytest.fixture
def llm_config() -> LLMConfig:
    return LLMConfig(provider="openai", api_key="sk-test", retry_delay=0)
