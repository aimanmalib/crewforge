"""Content pipeline through the fake endpoint (ported from contentforge integration tests)."""

from __future__ import annotations

import json

import pytest

from crewforge.core.config import LLMConfig
from crewforge.core.errors import CrewFailedError
from crewforge.recipes.content import ContentPipeline, ContentSettings, PipelineResult
from tests.recipes.content.fakes import agent_of, router


@pytest.fixture
def settings(tmp_path) -> ContentSettings:
    return ContentSettings(output_dir=str(tmp_path / "output"))


def _names(fake) -> list[str]:
    return [agent_of(c) for c in fake.calls]


class TestContentPipeline:
    async def test_full_pipeline_success(self, fake_llm, settings):
        fake_llm.responder = router()
        result = await ContentPipeline(LLMConfig(), settings).run("AI in Healthcare")
        assert result.ok
        assert result.total_tokens == 7 * 15  # exactly the fake provider's reported usage
        assert "research" in result.agent_results and "writer" in result.agent_results
        assert _names(fake_llm) == [
            "research",
            "outline",
            "writer",
            "seo",
            "editor",
            "quality",
            "publisher",
        ]
        assert result.quality_score == 90

    async def test_pipeline_with_translation(self, fake_llm, settings):
        settings.pipeline.enable_translation = True
        settings.pipeline.target_languages = ["zh"]
        fake_llm.responder = router()
        result = await ContentPipeline(LLMConfig(), settings).run("AI in Healthcare")
        assert "zh" in result.translations
        assert any(f.endswith("translation.zh.md") for f in result.output_files)

    async def test_pipeline_skips_seo_when_disabled(self, fake_llm, settings):
        settings.pipeline.seo_enabled = False
        settings.pipeline.max_iterations = 1
        fake_llm.responder = router()
        result = await ContentPipeline(LLMConfig(), settings).run("AI in Healthcare")
        assert result.ok
        assert "seo" not in result.agent_results and result.seo_analysis == ""
        assert len(fake_llm.calls) == 6

    def test_cli_passes_seo_and_format_to_config(self, fake_llm, tmp_path):
        from click.testing import CliRunner

        from crewforge.cli import main

        fake_llm.responder = router()
        out = tmp_path / "o"
        res = CliRunner().invoke(
            main, ["write", "Topic", "--no-seo", "-f", "markdown", "-f", "html", "-o", str(out)]
        )
        assert res.exit_code == 0, res.output
        assert "seo" not in _names(fake_llm)
        assert (out / "topic.md").exists() and (out / "topic.html").exists()

    async def test_pipeline_failure_at_research(self, fake_llm, settings):
        import httpx

        fake_llm.replies = [httpx.Response(400, json={"error": "API connection failed"})]
        with pytest.raises(CrewFailedError) as info:
            await ContentPipeline(LLMConfig(), settings).run("Test Topic")
        assert info.value.agents == ["research"]

    def test_agent_list(self, settings):
        agents = ContentPipeline(LLMConfig(api_key="k"), settings).get_agent_list()
        assert len(agents) == 8
        names = [a["name"] for a in agents]
        assert "research" in names and "publisher" in names

    async def test_metrics_file_holds_only_reported_usage(self, fake_llm, settings):
        fake_llm.responder = router()
        result = await ContentPipeline(LLMConfig(), settings).run("Topic")
        data = json.loads(open(result.metrics_path).read())
        assert data["total_tokens"] == 105 and data["calls"] == 7
        assert data["unreported_calls"] == 0


class TestPipelineResult:
    def test_ok_status(self):
        assert PipelineResult(status="success", article="content", total_tokens=1000).ok

    def test_failed_status(self):
        assert PipelineResult(status="failed").ok is False

    def test_summary(self):
        r = PipelineResult(
            article="# Article\nContent here", total_tokens=5000, pipeline_duration_s=12.5
        )
        summary = r.summary()
        assert summary["total_tokens"] == 5000 and summary["word_count"] > 0

    def test_summary_translations(self):
        r = PipelineResult(translations={"zh": "content", "ms": "content"})
        assert "zh" in r.summary()["translations"]
