"""Tests for IndexAgent."""

from __future__ import annotations

import pytest

from crewforge.recipes.docs import IndexAgent, IndexEntry


class TestIndexAgent:
    """Test the IndexAgent."""

    @pytest.mark.asyncio
    async def test_index_chunks(self, config, mock_client, sample_chunks):
        agent = IndexAgent()
        count = await agent.index_chunks(sample_chunks)
        assert count == 3

    @pytest.mark.asyncio
    async def test_search_keywords_finds_match(self, config, mock_client, sample_chunks):
        agent = IndexAgent()
        await agent.index_chunks(sample_chunks)
        results = agent.search_keywords("document analysis")
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_search_keywords_returns_tuples(self, config, mock_client, sample_chunks):
        agent = IndexAgent()
        await agent.index_chunks(sample_chunks)
        results = agent.search_keywords("pipeline agents")
        assert all(isinstance(r, tuple) and len(r) == 2 for r in results)

    @pytest.mark.asyncio
    async def test_compute_tfidf(self, config, mock_client, sample_chunks):
        agent = IndexAgent()
        await agent.index_chunks(sample_chunks)
        tfidf = agent.compute_tfidf("doc-abc-chunk-0000")
        assert isinstance(tfidf, dict)

    @pytest.mark.asyncio
    async def test_compute_tfidf_unknown_chunk(self, config, mock_client):
        agent = IndexAgent()
        assert agent.compute_tfidf("nonexistent") == {}

    @pytest.mark.asyncio
    async def test_get_entry(self, config, mock_client, sample_chunks):
        agent = IndexAgent()
        await agent.index_chunks(sample_chunks)
        entry = agent.get_entry("doc-abc-chunk-0000")
        assert entry is not None
        assert entry.document_id == "doc-abc"

    @pytest.mark.asyncio
    async def test_stats(self, config, mock_client, sample_chunks):
        agent = IndexAgent()
        await agent.index_chunks(sample_chunks)
        stats = agent.stats()
        assert stats["total_entries"] == 3
        assert stats["total_documents"] == 3
        assert stats["unique_terms"] > 0

    @pytest.mark.asyncio
    async def test_run_via_abstract_method(self, config, mock_client, sample_chunks):
        agent = IndexAgent()
        result = await agent.run(chunks=sample_chunks)
        assert result["indexed"] == 3

    def test_tokenize_removes_stop_words(self, config, mock_client):
        agent = IndexAgent()
        tokens = agent._tokenize("The quick brown fox is in the garden")
        assert "the" not in tokens
        assert "is" not in tokens
        assert "in" not in tokens
        assert "quick" in tokens

    def test_stop_words_include_malay(self, config, mock_client):
        agent = IndexAgent()
        assert "dan" in agent.STOP_WORDS
        assert "yang" in agent.STOP_WORDS


class TestIndexEntry:
    def test_creation(self):
        entry = IndexEntry(chunk_id="c1", document_id="d1", text="hello", keywords=["hello"])
        assert entry.chunk_id == "c1"
