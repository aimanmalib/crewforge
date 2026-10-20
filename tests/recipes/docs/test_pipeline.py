"""Tests for DocsPipeline."""

from __future__ import annotations

from crewforge.core.config import LLMConfig
from crewforge.recipes.docs import DocsPipeline, PipelineResult


class TestDocsPipeline:
    """Test the pipeline orchestrator."""

    def test_init_creates_all_agents(self, config):
        pipeline = DocsPipeline(LLMConfig(api_key="test-key-123"), config)
        assert pipeline.ingester is not None
        assert pipeline.indexer is not None
        assert pipeline.retriever is not None
        assert pipeline.answerer is not None
        assert pipeline.summarizer is not None
        assert pipeline.fact_checker is not None
        assert pipeline.citation_agent is not None
        assert pipeline.exporter is not None

    def test_init_uses_config(self, config):
        pipeline = DocsPipeline(LLMConfig(api_key="test-key-123"), config)
        assert pipeline.config.api_key == "test-key-123"
        assert pipeline.settings.chunk_size == 256

    def test_init_default_config(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "env-key")
        pipeline = DocsPipeline()
        assert pipeline.config.api_key == "env-key"

    def test_tracker_shared_across_agents(self, config):
        pipeline = DocsPipeline(LLMConfig(api_key="k"), config)
        assert pipeline.tracker is not None
        assert pipeline.answerer.tracker is pipeline.summarizer.tracker is pipeline.tracker


class TestPipelineResult:
    """Test PipelineResult dataclass."""

    def test_creation(self, sample_doc_path, config, mock_client):
        from crewforge.recipes.docs import Document, Summary, TextChunk

        doc = Document(
            "d1",
            "t.txt",
            "content",
            "text",
            chunks=[TextChunk("c1", "d1", "content", 0, 7)],
        )
        summary = Summary("d1", "t.txt", "summary", [], 1, 0.5)
        result = PipelineResult(document=doc, summary=summary)
        assert result.document.doc_id == "d1"
        assert len(result.answers) == 0
