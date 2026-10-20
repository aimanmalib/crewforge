"""Honest failure is a core feature: nothing empty or unparseable is ever a success.

These tests are the sabotage check for the two guards. Delete the blank-content
check in ``Agent.ask`` or the empty-result check in ``Crew._checked`` and the
matching tests below go red (verified while building crewforge; see README).
"""

from __future__ import annotations

import pytest

from crewforge.core import Agent, Crew, LLMConfig
from crewforge.core.errors import CrewFailedError, EmptyOutputError, OutputParseError


class Reviewer(Agent):
    name = "security"


# --- Guard 1: Agent.ask refuses blank completions --------------------------------


@pytest.mark.parametrize("blank", ["", "   ", "\n\t", None])
async def test_agent_ask_rejects_blank_completion(fake_llm, blank):
    fake_llm.replies = [{"choices": [{"message": {"content": blank}, "finish_reason": "length"}]}]
    agent = Reviewer(fake_llm.client())
    with pytest.raises(EmptyOutputError) as info:
        await agent.ask("review this")
    assert info.value.agent == "security"
    assert "finish_reason=length" in str(info.value)


async def test_blank_completion_still_counts_its_tokens(fake_llm):
    fake_llm.replies = [""]
    agent = Reviewer(fake_llm.client())
    with pytest.raises(EmptyOutputError):
        await agent.ask("x")
    assert agent.tracker.total_tokens == 15  # the provider billed it; we report it


async def test_agent_ask_allow_empty_is_an_explicit_opt_out(fake_llm):
    fake_llm.replies = [""]
    resp = await Reviewer(fake_llm.client()).ask("x", allow_empty=True)
    assert resp.content == ""


async def test_ask_json_rejects_prose_naming_the_agent(fake_llm):
    fake_llm.replies = ["The code looks secure to me."]
    with pytest.raises(OutputParseError) as info:
        await Reviewer(fake_llm.client()).ask_json("review")
    assert info.value.agent == "security"


# --- Guard 2: Crew never accepts an empty result as success ---------------------


async def _returns(value):
    return value


@pytest.mark.parametrize("nothing", [None, "", "  ", [], {}, ()])
async def test_crew_step_rejects_empty_result(nothing):
    crew = Crew("pipeline", LLMConfig(api_key="k"))
    with pytest.raises(CrewFailedError) as info:
        await crew.step("writer", _returns(nothing))
    assert info.value.agents == ["writer"]
    assert info.value.failures[0].kind == "empty"
    await crew.client.aclose()


async def test_crew_parallel_rejects_empty_result():
    crew = Crew("pipeline", LLMConfig(api_key="k"))
    with pytest.raises(CrewFailedError) as info:
        await crew.parallel({"style": _returns("fine"), "logic": _returns("")})
    assert info.value.agents == ["logic"]
    await crew.client.aclose()


async def test_crew_failure_message_names_crew_and_agent(fake_llm):
    fake_llm.replies = [""]
    async with Crew("review", LLMConfig()) as crew:
        with pytest.raises(CrewFailedError) as info:
            await crew.step("security", crew.agent(Reviewer).ask("x"))
    assert str(info.value).startswith("review failed — agent(s) 'security'")
