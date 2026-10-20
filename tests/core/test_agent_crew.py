"""Agent and Crew behaviour against the fake endpoint."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from pydantic import BaseModel

from crewforge.core import Agent, Crew, CrewFailedError, LLMConfig
from crewforge.core.errors import ConfigError, LLMHTTPError


class Writer(Agent):
    name = "writer"
    system_prompt = "You write."


class Critic(Agent):
    name = "critic"
    system_prompt = "You critique."
    temperature = 0.0


class Verdict(BaseModel):
    ok: bool


async def test_agent_sends_system_prompt_context_and_records_usage(fake_llm):
    fake_llm.replies = ["draft"]
    async with Crew("t", LLMConfig()) as crew:
        resp = await crew.agent(Writer).ask("write it", context="facts")
    assert resp.content == "draft"
    msgs = fake_llm.calls[0]["messages"]
    assert msgs[0] == {"role": "system", "content": "You write."}
    assert msgs[1]["content"] == "Context:\nfacts"
    assert msgs[2]["content"] == "write it"
    assert crew.tracker.by_agent()["writer"].total_tokens == 15


async def test_class_and_instance_overrides(fake_llm):
    async with Crew("t", LLMConfig()) as crew:
        await crew.agent(Critic).ask("x")
        await crew.agent(Writer, system_prompt="Custom.", model="m2", temperature=0.9).ask("y")
    assert fake_llm.calls[0]["temperature"] == 0.0
    assert fake_llm.calls[1]["messages"][0]["content"] == "Custom."
    assert fake_llm.calls[1]["model"] == "m2"
    assert fake_llm.calls[1]["temperature"] == 0.9


async def test_ask_json_with_schema(fake_llm):
    fake_llm.replies = ['```json\n{"ok": true}\n```']
    async with Crew("t", LLMConfig()) as crew:
        verdict = await crew.agent(Critic).ask_json("judge", schema=Verdict)
    assert verdict.ok is True


async def test_parallel_runs_concurrently_and_keeps_order(fake_llm):
    fake_llm.responder = lambda p: p["messages"][-1]["content"].upper()
    async with Crew("t", LLMConfig()) as crew:
        out = await crew.parallel(
            {"writer": crew.agent(Writer).ask("a"), "critic": crew.agent(Critic).ask("b")}
        )
    assert {k: v.content for k, v in out.items()} == {"writer": "A", "critic": "B"}
    assert list(out) == ["writer", "critic"]


async def test_parallel_require_all_names_every_failed_agent(fake_llm):
    fake_llm.responder = lambda p: "" if "a" == p["messages"][-1]["content"] else "fine"
    async with Crew("review", LLMConfig()) as crew:
        with pytest.raises(CrewFailedError) as info:
            await crew.parallel(
                {"writer": crew.agent(Writer).ask("a"), "critic": crew.agent(Critic).ask("b")}
            )
    assert info.value.agents == ["writer"]
    assert "writer" in str(info.value) and "empty" in str(info.value)


async def test_parallel_require_any_keeps_successes_and_records_failures(fake_llm):
    fake_llm.responder = lambda p: "" if p["messages"][-1]["content"] == "a" else "fine"
    async with Crew("review", LLMConfig()) as crew:
        out = await crew.parallel(
            {"writer": crew.agent(Writer).ask("a"), "critic": crew.agent(Critic).ask("b")},
            require="any",
        )
    assert list(out) == ["critic"]
    assert [f.agent for f in crew.failures] == ["writer"]
    assert crew.report()["status"] == "partial"


async def test_parallel_require_any_still_fails_when_nobody_succeeds(fake_llm):
    fake_llm.replies = [""]
    async with Crew("review", LLMConfig()) as crew:
        with pytest.raises(CrewFailedError) as info:
            await crew.parallel(
                {"writer": crew.agent(Writer).ask("a"), "critic": crew.agent(Critic).ask("b")},
                require="any",
            )
    assert sorted(info.value.agents) == ["critic", "writer"]


async def test_http_failure_is_attributed_to_the_agent(fake_llm):
    fake_llm.replies = [httpx.Response(401, json={"error": {"message": "invalid key"}})]
    async with Crew("t", LLMConfig()) as crew:
        with pytest.raises(CrewFailedError) as info:
            await crew.step("writer", crew.agent(Writer).ask("x"))
    failure = info.value.failures[0]
    assert (failure.agent, failure.kind) == ("writer", "http")
    assert isinstance(info.value.__cause__, LLMHTTPError)
    assert crew.tracker.by_agent()["writer"].errors == 1


async def test_crew_validates_config_before_any_call(fake_llm, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        Crew("t", LLMConfig())
    assert fake_llm.calls == []


async def test_cancellation_is_not_swallowed(fake_llm):
    async def never():
        raise asyncio.CancelledError

    async with Crew("t", LLMConfig()) as crew:
        with pytest.raises(asyncio.CancelledError):
            await crew.parallel({"x": never()})


async def test_allow_empty_opt_out(fake_llm):
    async with Crew("t", LLMConfig()) as crew:
        assert await crew.step("lister", _value([]), allow_empty=True) == []


async def _value(v):
    return v


async def test_retries_are_recorded_per_agent(fake_llm):
    responses = [httpx.Response(503), "recovered"]
    fake_llm.responder = lambda p: responses.pop(0)
    async with Crew("t", LLMConfig(retry_delay=0)) as crew:
        resp = await crew.agent(Writer).ask("x")
    assert resp.content == "recovered" and resp.attempts == 2
    usage = crew.tracker.by_agent()["writer"]
    assert (usage.calls, usage.retries) == (1, 1)
    assert fake_llm.sleeps == [0]
