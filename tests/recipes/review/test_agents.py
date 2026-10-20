"""Review agents (ported from codeguard tests/unit/test_agents.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from crewforge.core.agent import Agent
from crewforge.core.errors import EmptyOutputError, OutputParseError
from crewforge.recipes.review.agents import AGENT_REGISTRY, AgentResult, get_agent
from tests.recipes.review.fakes import SUMMARY, make_response


class TestAgentRegistry:
    def test_all_7_registered(self):
        assert len(AGENT_REGISTRY) == 7

    def test_expected_agents(self):
        assert set(AGENT_REGISTRY) == {
            "security",
            "style",
            "complexity",
            "logic",
            "testing",
            "documentation",
            "summary",
        }

    def test_get_valid(self, agent_setup):
        client, tracker = agent_setup
        for name in AGENT_REGISTRY:
            agent = get_agent(name, client=client, tracker=tracker)
            assert agent.name == name
            assert isinstance(agent, Agent)

    def test_get_invalid(self, agent_setup):
        client, tracker = agent_setup
        with pytest.raises(ValueError):
            get_agent("nonexistent", client=client, tracker=tracker)


class TestAgentResult:
    def test_defaults(self):
        r = AgentResult(agent_name="test")
        assert r.ok
        assert r.finding_count == 0

    def test_severity_counts(self):
        r = AgentResult(
            agent_name="test",
            findings=[
                {"severity": "critical"},
                {"severity": "error"},
                {"severity": "warning"},
                {"severity": "warning"},
            ],
        )
        assert (r.critical_count, r.error_count, r.warning_count, r.finding_count) == (1, 1, 2, 4)


class TestIndividualAgents:
    @pytest.mark.parametrize(
        "name,code",
        [
            ("security", "def foo(): pass"),
            ("style", "x = 1"),
            ("complexity", "def f(): pass"),
            ("logic", "x = 1/0"),
            ("testing", "def add(a,b): return a+b"),
            ("documentation", "def f(): pass"),
        ],
    )
    async def test_reviewer_agent(self, agent_setup, name, code):
        # codeguard had one test per agent (test_security_agent ... test_documentation_agent)
        client, tracker = agent_setup
        client.chat = AsyncMock(return_value=make_response('{"findings": [], "summary": "ok"}'))
        agent = get_agent(name, client=client, tracker=tracker)
        result = await agent.execute(code=code, language="python")
        assert result.ok
        assert result.tokens_used > 0
        assert result.findings == [] and result.summary == "ok"

    async def test_summary_agent(self, agent_setup):
        client, tracker = agent_setup
        client.chat = AsyncMock(return_value=make_response(SUMMARY))
        agent = get_agent("summary", client=client, tracker=tracker)
        result = await agent.execute(code="code", context="all findings here")
        assert result.ok
        assert result.data["decision"] == "REQUEST_CHANGES"
        prompt = client.chat.await_args.args[0][-1].content
        assert "all findings here" in prompt  # codeguard never passed findings to the prompt

    async def test_findings_are_parsed_and_severities_normalised(self, agent_setup):
        client, tracker = agent_setup
        client.chat = AsyncMock(
            return_value=make_response(
                '```json\n{"findings":[{"severity":"High","title":"t"}],"summary":"s"}\n```'
            )
        )
        result = await get_agent("logic", client=client, tracker=tracker).execute(code="x")
        assert result.findings[0]["severity"] == "error"

    async def test_prose_reply_is_a_parse_failure_naming_the_agent(self, agent_setup):
        client, tracker = agent_setup
        client.chat = AsyncMock(return_value=make_response("Looks good to me!"))
        with pytest.raises(OutputParseError) as info:
            await get_agent("style", client=client, tracker=tracker).execute(code="x")
        assert info.value.agent == "style"

    async def test_empty_reply_is_a_failure_naming_the_agent(self, agent_setup):
        client, tracker = agent_setup
        client.chat = AsyncMock(return_value=make_response(""))
        with pytest.raises(EmptyOutputError) as info:
            await get_agent("security", client=client, tracker=tracker).execute(code="x")
        assert info.value.agent == "security"

    async def test_unknown_severity_is_rejected(self, agent_setup):
        client, tracker = agent_setup
        client.chat = AsyncMock(
            return_value=make_response('{"findings":[{"severity":"catastrophic"}]}')
        )
        with pytest.raises(OutputParseError, match="severity"):
            await get_agent("logic", client=client, tracker=tracker).execute(code="x")
