"""Unit tests for all 8 content agents (ported from contentforge tests/unit/test_agents.py)."""

import json
from unittest.mock import AsyncMock

import pytest

from crewforge.core.agent import Agent
from crewforge.core.client import ChatResponse, Usage
from crewforge.core.errors import EmptyOutputError, OutputParseError
from crewforge.recipes.content.agents import (
    AGENT_REGISTRY,
    AgentResult,
    ContentAgent,
    EditorAgent,
    OutlineAgent,
    PublisherAgent,
    QualityAgent,
    ResearchAgent,
    SEOAgent,
    TranslatorAgent,
    WriterAgent,
    get_agent,
)

BaseAgent = ContentAgent


def make_test_response(content='{"test": "data"}', prompt=500, comp=300):
    return ChatResponse(
        content=content,
        usage=Usage(prompt, comp, prompt + comp, reported=True),
        model="mimo-v2.5-pro",
        latency_ms=100.0,
    )


class TestAgentResult:
    def test_default_status(self):
        r = AgentResult(agent_name="test")
        assert r.status == "success"
        assert r.ok is True

    def test_failed_status(self):
        r = AgentResult(agent_name="test", status="failed")
        assert r.ok is False

    def test_partial_is_not_ok(self):
        r = AgentResult(agent_name="test", status="partial")
        assert r.ok is False  # only 'success' is ok

    def test_metadata_default_empty(self):
        r = AgentResult(agent_name="test")
        assert r.metadata == {}

    def test_error_field(self):
        r = AgentResult(agent_name="test", status="failed", error="timeout")
        assert r.error == "timeout"

    def test_tokens_used(self):
        r = AgentResult(agent_name="test", tokens_used=1500)
        assert r.tokens_used == 1500

    def test_latency_tracking(self):
        r = AgentResult(agent_name="test", latency_ms=250.5)
        assert r.latency_ms == 250.5

    def test_reasoning_field(self):
        r = AgentResult(agent_name="test", reasoning="step by step...")
        assert r.reasoning == "step by step..."


class TestAgentRegistry:
    def test_all_8_registered(self):
        assert len(AGENT_REGISTRY) == 8

    def test_expected_names(self):
        expected = {
            "research",
            "outline",
            "writer",
            "seo",
            "editor",
            "translator",
            "quality",
            "publisher",
        }
        assert set(AGENT_REGISTRY.keys()) == expected

    def test_get_valid_agent(self, config, mock_client, tracker):
        for name in AGENT_REGISTRY:
            agent = get_agent(name, config=config, client=mock_client, tracker=tracker)
            assert agent.name == name

    def test_get_invalid_raises(self, config, mock_client, tracker):
        with pytest.raises(ValueError, match="Unknown agent"):
            get_agent("nonexistent", config=config, client=mock_client, tracker=tracker)

    def test_legacy_call_mimo_alias(self):
        # contentforge aliased _call_mimo to _call_llm; every content agent now
        # inherits the single core LLM entry point (and its empty-output guard).
        assert issubclass(BaseAgent, Agent)
        assert BaseAgent.ask is Agent.ask

    def test_all_subclass_base(self, config, mock_client, tracker):
        for name in AGENT_REGISTRY:
            agent = get_agent(name, config=config, client=mock_client, tracker=tracker)
            assert isinstance(agent, BaseAgent)


class TestResearchAgent:
    def test_name(self, config, mock_client, tracker):
        a = ResearchAgent(config=config, client=mock_client, tracker=tracker)
        assert a.name == "research"

    def test_has_system_prompt(self, config, mock_client, tracker):
        a = ResearchAgent(config=config, client=mock_client, tracker=tracker)
        assert "Research Agent" in a.system_prompt

    @pytest.mark.asyncio
    async def test_execute_returns_result(self, config, mock_client, tracker):
        mock_client.chat = AsyncMock(
            return_value=make_test_response('{"topic": "AI", "key_subtopics": [{"title": "ML"}]}')
        )
        a = ResearchAgent(config=config, client=mock_client, tracker=tracker)
        result = await a.execute(topic="AI in Healthcare")
        assert result.ok
        assert result.metadata["topic"] == "AI in Healthcare"

    @pytest.mark.asyncio
    async def test_run_handles_error(self, config, mock_client, tracker):
        mock_client.chat = AsyncMock(side_effect=Exception("API down"))
        a = ResearchAgent(config=config, client=mock_client, tracker=tracker)
        result = await a.run(topic="Test")
        assert result.status == "failed"
        assert "API down" in result.error


class TestOutlineAgent:
    def test_name(self, config, mock_client, tracker):
        a = OutlineAgent(config=config, client=mock_client, tracker=tracker)
        assert a.name == "outline"

    @pytest.mark.asyncio
    async def test_execute_with_research(self, config, mock_client, tracker):
        mock_client.chat = AsyncMock(
            return_value=make_test_response('{"title": "Guide", "sections": []}')
        )
        a = OutlineAgent(config=config, client=mock_client, tracker=tracker)
        result = await a.execute(research_data="data", target_words=2000)
        assert result.ok
        assert result.metadata["target_words"] == 2000


class TestWriterAgent:
    def test_name(self, config, mock_client, tracker):
        a = WriterAgent(config=config, client=mock_client, tracker=tracker)
        assert a.name == "writer"

    @pytest.mark.asyncio
    async def test_execute_produces_content(self, config, mock_client, tracker):
        mock_client.chat = AsyncMock(
            return_value=make_test_response("# AI Guide\n\nComprehensive content here.")
        )
        a = WriterAgent(config=config, client=mock_client, tracker=tracker)
        result = await a.execute(outline="Outline", research_data="Research")
        assert result.ok
        assert result.metadata["word_count"] > 0


class TestSEOAgent:
    def test_name(self, config, mock_client, tracker):
        a = SEOAgent(config=config, client=mock_client, tracker=tracker)
        assert a.name == "seo"

    @pytest.mark.asyncio
    async def test_execute_analyzes(self, config, mock_client, tracker):
        mock_client.chat = AsyncMock(return_value=make_test_response('{"seo_score": 85}'))
        a = SEOAgent(config=config, client=mock_client, tracker=tracker)
        result = await a.execute(content="# Article", target_keywords=["AI"])
        assert result.ok
        assert result.metadata["target_keywords"] == ["AI"]


class TestEditorAgent:
    def test_name(self, config, mock_client, tracker):
        a = EditorAgent(config=config, client=mock_client, tracker=tracker)
        assert a.name == "editor"

    @pytest.mark.asyncio
    async def test_execute_refines(self, config, mock_client, tracker):
        mock_client.chat = AsyncMock(
            return_value=make_test_response("# Refined Article\n\nPolished.")
        )
        a = EditorAgent(config=config, client=mock_client, tracker=tracker)
        result = await a.execute(content="Draft", seo_recommendations="Tips")
        assert result.ok


class TestTranslatorAgent:
    def test_name(self, config, mock_client, tracker):
        a = TranslatorAgent(config=config, client=mock_client, tracker=tracker)
        assert a.name == "translator"

    @pytest.mark.asyncio
    async def test_execute_translates(self, config, mock_client, tracker):
        mock_client.chat = AsyncMock(
            return_value=make_test_response("# AI Guide\n\nChinese content.")
        )
        a = TranslatorAgent(config=config, client=mock_client, tracker=tracker)
        result = await a.execute(content="# AI", target_language="zh")
        assert result.ok
        assert result.metadata["target_language"] == "zh"

    @pytest.mark.asyncio
    async def test_preserves_keywords(self, config, mock_client, tracker):
        mock_client.chat = AsyncMock(return_value=make_test_response("MiMo is great"))
        a = TranslatorAgent(config=config, client=mock_client, tracker=tracker)
        result = await a.execute(content="text", target_language="ms", preserve_keywords=["MiMo"])
        assert result.ok


class TestQualityAgent:
    def test_name(self, config, mock_client, tracker):
        a = QualityAgent(config=config, client=mock_client, tracker=tracker)
        assert a.name == "quality"

    @pytest.mark.asyncio
    async def test_execute_passes_threshold(self, config, mock_client, tracker):
        report = json.dumps({"overall_score": 90, "pass_threshold": True})
        mock_client.chat = AsyncMock(return_value=make_test_response(report))
        a = QualityAgent(config=config, client=mock_client, tracker=tracker)
        result = await a.execute(content="Good article", threshold=0.8)
        assert result.metadata["passes_threshold"] is True

    @pytest.mark.asyncio
    async def test_execute_fails_threshold(self, config, mock_client, tracker):
        report = json.dumps({"overall_score": 50, "pass_threshold": False})
        mock_client.chat = AsyncMock(return_value=make_test_response(report))
        a = QualityAgent(config=config, client=mock_client, tracker=tracker)
        result = await a.execute(content="Bad article", threshold=0.8)
        assert result.metadata["passes_threshold"] is False

    @pytest.mark.asyncio
    async def test_execute_parses_fenced_json(self, config, mock_client, tracker):
        """Real models usually wrap JSON in ```json fences; the score must still parse."""
        report = 'Here is my evaluation:\n```json\n{"overall_score": "87", "dimensions": {}}\n```'
        mock_client.chat = AsyncMock(return_value=make_test_response(report))
        a = QualityAgent(config=config, client=mock_client, tracker=tracker)
        result = await a.execute(content="Good article", threshold=0.8)
        assert result.metadata["overall_score"] == 87
        assert result.metadata["passes_threshold"] is True


class TestPublisherAgent:
    def test_name(self, config, mock_client, tracker):
        a = PublisherAgent(config=config, client=mock_client, tracker=tracker)
        assert a.name == "publisher"

    @pytest.mark.asyncio
    async def test_execute_creates_files(self, config, mock_client, tracker):
        output = json.dumps({"formats": {"markdown": "content"}, "metadata": {"title": "T"}})
        mock_client.chat = AsyncMock(return_value=make_test_response(output))
        a = PublisherAgent(config=config, client=mock_client, tracker=tracker)
        result = await a.execute(
            content="# Article",
            title="Test",
            publish_targets=["markdown"],
            output_dir=config.output_dir,
        )
        assert result.ok
        assert any(f.endswith("test.md") for f in result.metadata["output_files"])


class TestBaseAgentConfig:
    def test_system_prompt_override(self, config, mock_client, tracker):
        from crewforge.recipes.content import AgentConfig

        config.agents = [AgentConfig(name="research", system_prompt_override="Custom")]
        a = ResearchAgent(config=config, client=mock_client, tracker=tracker)
        assert a.effective_system_prompt == "Custom"

    def test_default_system_prompt(self, config, mock_client, tracker):
        a = ResearchAgent(config=config, client=mock_client, tracker=tracker)
        assert "Research Agent" in a.effective_system_prompt


class TestHonestAgents:
    """New in crewforge: the agents refuse output they cannot use."""

    @pytest.mark.asyncio
    async def test_quality_prose_is_a_parse_error(self, config, mock_client, tracker):
        mock_client.chat = AsyncMock(return_value=make_test_response("Great article, 9/10!"))
        with pytest.raises(OutputParseError) as info:
            await QualityAgent(config=config, client=mock_client, tracker=tracker).execute(
                content="x"
            )
        assert info.value.agent == "quality"

    @pytest.mark.asyncio
    async def test_quality_without_score_is_a_parse_error(self, config, mock_client, tracker):
        mock_client.chat = AsyncMock(return_value=make_test_response('{"dimensions": {}}'))
        with pytest.raises(OutputParseError, match="overall_score"):
            await QualityAgent(config=config, client=mock_client, tracker=tracker).execute(
                content="x"
            )

    @pytest.mark.asyncio
    async def test_quality_score_out_of_range(self, config, mock_client, tracker):
        mock_client.chat = AsyncMock(return_value=make_test_response('{"overall_score": 870}'))
        with pytest.raises(OutputParseError, match="outside 0-100"):
            await QualityAgent(config=config, client=mock_client, tracker=tracker).execute(
                content="x"
            )

    @pytest.mark.asyncio
    async def test_empty_writer_raises_naming_writer(self, config, mock_client, tracker):
        mock_client.chat = AsyncMock(return_value=make_test_response(""))
        with pytest.raises(EmptyOutputError) as info:
            await WriterAgent(config=config, client=mock_client, tracker=tracker).execute(
                outline="o"
            )
        assert info.value.agent == "writer"

    @pytest.mark.asyncio
    async def test_agent_overrides_reach_the_request(self, config, mock_client, tracker):
        from crewforge.recipes.content import AgentConfig

        config.agents = [AgentConfig(name="writer", model_override="m2", temperature_override=0.0)]
        mock_client.chat = AsyncMock(return_value=make_test_response("text"))
        await WriterAgent(config=config, client=mock_client, tracker=tracker).execute(outline="o")
        kwargs = mock_client.chat.await_args.kwargs
        assert kwargs["model"] == "m2" and kwargs["temperature"] == 0.0
