"""ApiPipeline through the fake endpoint (ported from apiforge tests/test_pipeline.py)."""

from __future__ import annotations

import pytest

from crewforge.core.config import LLMConfig
from crewforge.core.errors import CrewFailedError
from crewforge.recipes.api.pipeline import ApiPipeline, PipelineResult
from tests.recipes.api.fakes import agent_of, router


class TestPipeline:
    def test_init_creates_agents(self, config):
        p = ApiPipeline(config)
        assert p.config is config and p.validator is not None

    def test_default_config(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        assert ApiPipeline().config.api_key == "k"

    @pytest.mark.asyncio
    async def test_generate_returns_result(self, fake_llm):
        fake_llm.responder = router()
        result = await ApiPipeline(LLMConfig()).generate("todo API")
        assert isinstance(result, PipelineResult)
        assert set(result.openapi_spec["paths"]) == {"/todos", "/todos/{id}"}
        assert result.validation.valid and result.validation.operations == 3
        assert sorted(agent_of(c) for c in fake_llm.calls) == [
            "auth",
            "doc_gen",
            "model",
            "parser",
            "router",
        ]
        assert result.token_summary["total_tokens"] == 5 * 15

    @pytest.mark.asyncio
    async def test_parser_failure_stops_before_other_agents(self, fake_llm):
        fake_llm.responder = router({"parser": '{"title": "x", "endpoints": []}'})
        with pytest.raises(CrewFailedError) as info:
            await ApiPipeline(LLMConfig()).generate("todo API")
        assert info.value.agents == ["parser"]
        assert len(fake_llm.calls) == 1

    @pytest.mark.asyncio
    async def test_no_models_skips_the_model_call(self, fake_llm):
        import json

        from tests.recipes.api.fakes import TODO_SPEC

        spec = json.loads(TODO_SPEC)
        spec["models"] = []
        fake_llm.responder = router({"parser": json.dumps(spec)})
        result = await ApiPipeline(LLMConfig()).generate("todo API")
        assert "model" not in [agent_of(c) for c in fake_llm.calls]
        compile(result.model_code, "models.py", "exec")
