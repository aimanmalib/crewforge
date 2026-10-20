import pytest

from crewforge.core import Agent, Crew, CrewFailedError, LLMConfig


class Echo(Agent):
    name = "echo"


async def test_crew_step_returns_text(fake_llm):
    fake_llm.replies = ["hello"]
    async with Crew("demo", LLMConfig()) as crew:
        resp = await crew.step("echo", crew.agent(Echo).ask("hi"))
    assert resp.content == "hello"
    assert crew.tracker.total_tokens == 15


async def test_crew_names_agent_on_empty(fake_llm):
    fake_llm.replies = ["   "]
    async with Crew("demo", LLMConfig()) as crew:
        with pytest.raises(CrewFailedError) as info:
            await crew.step("echo", crew.agent(Echo).ask("hi"))
    assert info.value.agents == ["echo"]
