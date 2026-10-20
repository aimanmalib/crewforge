"""Tests for AnswerAgent."""

from __future__ import annotations

import pytest

from crewforge.recipes.docs import Answer, AnswerAgent, RetrievalResult


class TestAnswerAgent:
    """Test the AnswerAgent."""

    @pytest.mark.asyncio
    async def test_answer_returns_answer(self, config, mock_client, tracker):
        agent = AnswerAgent(mock_client, tracker)
        chunks = [
            RetrievalResult("c1", "d1", "MiMo is a powerful language model.", 0.9),
        ]
        result = await agent.answer("What is MiMo?", chunks)
        assert isinstance(result, Answer)

    @pytest.mark.asyncio
    async def test_answer_has_citations(self, config, mock_client, mock_response, tracker):
        mock_client.chat.return_value = mock_response(
            content="MiMo is great [Source 1]. Very powerful.",
            prompt_tokens=100,
            completion_tokens=50,
        )
        agent = AnswerAgent(mock_client, tracker)
        chunks = [RetrievalResult("c1", "d1", "MiMo is great.", 0.9)]
        result = await agent.answer("Describe MiMo.", chunks)
        assert isinstance(result, Answer)

    @pytest.mark.asyncio
    async def test_answer_tracks_tokens(self, config, mock_client, tracker):
        agent = AnswerAgent(mock_client, tracker)
        chunks = [RetrievalResult("c1", "d1", "test content", 0.8)]
        await agent.answer("test?", chunks)
        assert tracker.total_calls >= 1

    @pytest.mark.asyncio
    async def test_run_method(self, config, mock_client, tracker):
        agent = AnswerAgent(mock_client, tracker)
        chunks = [RetrievalResult("c1", "d1", "content here", 0.8)]
        result = await agent.run(question="test?", chunks=chunks)
        assert isinstance(result, Answer)

    def test_system_prompt(self, config, mock_client, tracker):
        agent = AnswerAgent(mock_client, tracker)
        prompt = agent.effective_system_prompt
        assert "STRICTLY" in prompt or "strictly" in prompt.lower()

    def test_build_context(self, config, mock_client, tracker):
        agent = AnswerAgent(mock_client, tracker)
        chunks = [
            RetrievalResult("c1", "d1", "text one", 0.9),
            RetrievalResult("c2", "d1", "text two", 0.8),
        ]
        ctx = agent._build_context(chunks)
        assert "[Source 1]" in ctx
        assert "[Source 2]" in ctx
