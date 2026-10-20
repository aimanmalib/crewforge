"""Tests for TestAgent."""

import pytest

from crewforge.recipes.api.agents import APIDescription, ParsedEndpoint, TestAgent


class TestTestAgent:
    @pytest.mark.asyncio
    async def test_generate_tests(self, config, mock_client, tracker):
        desc = APIDescription(
            title="T",
            description="D",
            endpoints=[ParsedEndpoint(path="/items", method="GET", description="List")],
        )
        agent = TestAgent(mock_client, tracker)
        code = await agent.generate_tests(desc)
        assert "def test_" in code
        assert "/items" in code

    @pytest.mark.asyncio
    async def test_generate_multiple_endpoints(self, config, mock_client, tracker):
        desc = APIDescription(
            title="T",
            description="D",
            endpoints=[
                ParsedEndpoint(path="/users", method="GET", description="List users"),
                ParsedEndpoint(path="/users", method="POST", description="Create user"),
            ],
        )
        agent = TestAgent(mock_client, tracker)
        code = await agent.generate_tests(desc)
        assert code.count("def test_") == 2

    @pytest.mark.asyncio
    async def test_run(self, config, mock_client, tracker):
        desc = APIDescription(
            title="T",
            description="D",
            endpoints=[ParsedEndpoint(path="/x", method="GET", description="X")],
        )
        agent = TestAgent(mock_client, tracker)
        code = await agent.run(description=desc)
        assert isinstance(code, str)
