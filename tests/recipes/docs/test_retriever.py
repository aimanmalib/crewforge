"""Tests for RetrieverAgent."""

from __future__ import annotations

import pytest

from crewforge.recipes.docs import IndexAgent, RetrievalResult, RetrieverAgent


class TestRetrieverAgent:
    """Test the RetrieverAgent."""

    @pytest.mark.asyncio
    async def test_retrieve_finds_chunks(self, config, mock_client, sample_chunks):
        indexer = IndexAgent()
        await indexer.index_chunks(sample_chunks)

        agent = RetrieverAgent(config, index=indexer)
        results = await agent.retrieve("document analysis")
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_retrieve_returns_sorted(self, config, mock_client, sample_chunks):
        indexer = IndexAgent()
        await indexer.index_chunks(sample_chunks)

        agent = RetrieverAgent(config, index=indexer)
        results = await agent.retrieve("pipeline agents methods")
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_retrieve_respects_top_k(self, config, mock_client, sample_chunks):
        indexer = IndexAgent()
        await indexer.index_chunks(sample_chunks)

        agent = RetrieverAgent(config, index=indexer)
        results = await agent.retrieve("document", top_k=1)
        assert len(results) <= 1

    @pytest.mark.asyncio
    async def test_retrieve_without_index_raises(self, config, mock_client):
        agent = RetrieverAgent(mock_client)
        with pytest.raises(ValueError, match="IndexAgent not set"):
            await agent.retrieve("test query")

    @pytest.mark.asyncio
    async def test_retrieve_no_match(self, config, mock_client, sample_chunks):
        indexer = IndexAgent()
        await indexer.index_chunks(sample_chunks)

        agent = RetrieverAgent(config, index=indexer)
        results = await agent.retrieve("xyzzynonexistent")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_run_method(self, config, mock_client, sample_chunks):
        indexer = IndexAgent()
        await indexer.index_chunks(sample_chunks)

        agent = RetrieverAgent(config, index=indexer)
        results = await agent.run(query="MiMo model reasoning")
        assert isinstance(results, list)

    def test_retrieval_result_dataclass(self):
        r = RetrievalResult(chunk_id="c1", document_id="d1", text="hello", score=0.95)
        assert r.score == 0.95
        assert r.section == ""
