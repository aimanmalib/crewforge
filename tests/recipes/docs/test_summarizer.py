"""Tests for SummarizerAgent."""

from __future__ import annotations

import pytest

from crewforge.recipes.docs import Document, SummarizerAgent, Summary, TextChunk
from tests.recipes.docs.fakes import completion


class TestSummarizerAgent:
    """Test the SummarizerAgent."""

    @pytest.fixture
    def sample_doc(self):
        chunks = [
            TextChunk(f"c{i}", "d1", f"Paragraph {i} content. " * 10, 0, 100) for i in range(3)
        ]
        return Document(
            doc_id="d1",
            filename="test.txt",
            content="Paragraph 0. " * 50 + "Paragraph 1. " * 50 + "Paragraph 2. " * 50,
            file_type="text",
            chunks=chunks,
        )

    @pytest.mark.asyncio
    async def test_summarize_returns_summary(self, config, mock_client, tracker, sample_doc):
        mock_client.chat.return_value = completion(
            content="This is a summary.\n• Point one\n• Point two",
            prompt_tokens=200,
            completion_tokens=100,
            total_tokens=300,
        )
        agent = SummarizerAgent(mock_client, tracker)
        result = await agent.summarize(sample_doc)
        assert isinstance(result, Summary)

    @pytest.mark.asyncio
    async def test_summarize_extracts_key_points(self, config, mock_client, tracker, sample_doc):
        from tests.recipes.docs.fakes import completion

        mock_client.chat.return_value = completion(
            content="Summary text.\n• Key point 1\n• Key point 2\n• Key point 3",
            prompt_tokens=200,
            completion_tokens=100,
            total_tokens=300,
        )
        agent = SummarizerAgent(mock_client, tracker)
        result = await agent.summarize(sample_doc)
        assert len(result.key_points) >= 2

    @pytest.mark.asyncio
    async def test_run_method(self, config, mock_client, tracker, sample_doc):
        from tests.recipes.docs.fakes import completion

        mock_client.chat.return_value = completion(
            content="Summary here.",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        agent = SummarizerAgent(mock_client, tracker)
        result = await agent.run(document=sample_doc)
        assert isinstance(result, Summary)


class TestSummary:
    def test_dataclass(self):
        s = Summary(
            document_id="d1",
            filename="f.txt",
            summary_text="sum",
            key_points=["a"],
            word_count=1,
            compression_ratio=0.1,
        )
        assert s.document_id == "d1"
