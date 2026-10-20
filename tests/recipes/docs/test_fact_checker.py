"""Tests for FactCheckAgent."""

from __future__ import annotations

import pytest

from crewforge.recipes.docs import Answer, FactCheckAgent, FactCheckResult, RetrievalResult


class TestFactCheckAgent:
    """Test the FactCheckAgent."""

    @pytest.fixture
    def sample_answer(self):
        return Answer(
            question="What is MiMo?",
            answer_text="MiMo is a language model by Xiaomi.",
            citations=[],
            confidence="high",
        )

    @pytest.fixture
    def sample_chunks(self):
        return [RetrievalResult("c1", "d1", "MiMo is developed by Xiaomi.", 0.9)]

    @pytest.mark.asyncio
    async def test_check_returns_result(
        self, config, mock_client, tracker, sample_answer, sample_chunks
    ):
        from tests.recipes.docs.fakes import completion

        mock_client.chat.return_value = completion(
            content="Claim: MiMo by Xiaomi — VERIFIED\nOVERALL: verified",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        agent = FactCheckAgent(mock_client, tracker)
        result = await agent.check(sample_answer, sample_chunks)
        assert isinstance(result, FactCheckResult)

    @pytest.mark.asyncio
    async def test_check_detects_verified(
        self, config, mock_client, tracker, sample_answer, sample_chunks
    ):
        from tests.recipes.docs.fakes import completion

        mock_client.chat.return_value = completion(
            content="Claim 1: VERIFIED\nOVERALL: verified",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        agent = FactCheckAgent(mock_client, tracker)
        result = await agent.check(sample_answer, sample_chunks)
        assert result.overall_verdict == "verified"

    @pytest.mark.asyncio
    async def test_run_method(self, config, mock_client, tracker, sample_answer, sample_chunks):
        from tests.recipes.docs.fakes import completion

        mock_client.chat.return_value = completion(
            content="All verified. OVERALL: verified",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        agent = FactCheckAgent(mock_client, tracker)
        result = await agent.run(answer=sample_answer, source_chunks=sample_chunks)
        assert isinstance(result, FactCheckResult)
