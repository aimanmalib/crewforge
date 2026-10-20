"""Base agent of the api recipe (ported from apiforge tests/test_base_agent.py)."""

import pytest

from crewforge.recipes.api.agents import ApiAgent as BaseAgent
from tests.recipes.api.fakes import completion


class ConcreteAgent(BaseAgent):
    name = "test"
    system_prompt = "You are test, a specialized agent in the API scaffolding crew."

    async def run(self, **kwargs):
        return "done"


class TestBaseAgent:
    def test_init(self, tracker):
        assert ConcreteAgent(tracker=tracker).name == "test"

    def test_repr(self, tracker):
        assert "test" in repr(ConcreteAgent(tracker=tracker))

    def test_system_prompt(self, tracker):
        assert "test" in ConcreteAgent(tracker=tracker).effective_system_prompt

    @pytest.mark.asyncio
    async def test_call_mimo(self, mock_client, tracker):
        # apiforge's _call_mimo is crewforge's Agent.ask
        mock_client.chat.return_value = completion("response", 10, 5)
        resp = await ConcreteAgent(mock_client, tracker).ask("test prompt")
        assert resp.content == "response"
        assert tracker.total_calls == 1

    @pytest.mark.asyncio
    async def test_run(self, mock_client, tracker):
        assert await ConcreteAgent(mock_client, tracker).run() == "done"
