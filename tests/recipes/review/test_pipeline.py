"""Review crew against the fake endpoint (ported from codeguard test_orchestrator.py)."""

from __future__ import annotations

import pytest

from crewforge.core.errors import CrewFailedError
from crewforge.recipes.review.pipeline import CodeReviewCrew
from tests.recipes.review.fakes import router


async def test_successful_review_runs_summary(fake_llm, config):
    fake_llm.responder = router()
    result = await CodeReviewCrew(config).review("x = 1", "python")
    assert result.ok and result.status == "success"
    assert all(r.ok for r in result.agent_results.values())
    assert result.summary_result is not None
    assert result.summary_result.data["decision"] == "REQUEST_CHANGES"
    assert len(fake_llm.calls) == 7
    assert result.total_tokens == 7 * 15  # exactly what the fake provider reported
    assert result.total_findings == 1


async def test_all_agents_failing_marks_review_failed(fake_llm, config):
    import httpx

    fake_llm.replies = [httpx.Response(401, json={"error": {"message": "401 Unauthorized"}})]
    with pytest.raises(CrewFailedError) as info:
        await CodeReviewCrew(config).review("x = 1", "python")
    assert "401" in str(info.value)
    assert len(info.value.agents) == 6
    assert len(fake_llm.calls) == 6  # summary agent is skipped, 401 is not retried


async def test_one_failed_reviewer_fails_strict_run(fake_llm, config):
    fake_llm.responder = router({"logic": ""})
    with pytest.raises(CrewFailedError) as info:
        await CodeReviewCrew(config).review("x = 1")
    assert info.value.agents == ["logic"]


async def test_allow_partial_keeps_going_and_records_failure(fake_llm, config):
    fake_llm.responder = router({"logic": "no json, sorry"})
    result = await CodeReviewCrew(config, allow_partial=True).review("x = 1")
    assert result.status == "partial"
    assert result.failed_agents == ["logic"]
    assert result.agent_results["logic"].kind == "parse"
    summary_prompt = fake_llm.calls[-1]["messages"][-1]["content"]
    assert "SECURITY" in summary_prompt and "LOGIC" not in summary_prompt


async def test_agent_subset(fake_llm, config):
    fake_llm.responder = router()
    result = await CodeReviewCrew(config, agents=["security"]).review("x")
    assert list(result.agent_results) == ["security"]
    assert len(fake_llm.calls) == 2
