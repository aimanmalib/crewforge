"""The academic crew through the fake endpoint: plan, feedback, cite."""

from __future__ import annotations

import json

import httpx
import pytest

from crewforge.core.errors import CrewFailedError
from crewforge.recipes.academic.pipeline import (
    AcademicCrew,
    allocate_words,
    paragraphs,
    quote_in,
    trim_words,
)
from tests.recipes.academic.fakes import PLAN, agent_of, feedback_reply, router

DRAFT = (
    "Artificial intelligence is reshaping classrooms in Malaysia.\n\n"
    "Teachers use chatbots to prepare lessons (Tan, 2021).\n\n"
    "However, rural schools lack devices."
)


class TestAllocateWords:
    def test_scales_to_target_exactly(self):
        budget = allocate_words([100, 400, 400, 100], 1500)
        assert sum(budget) == 1500
        assert budget == [150, 600, 600, 150]

    def test_rounds_to_tens_and_puts_remainder_on_largest(self):
        budget = allocate_words([1, 1, 1], 1000)
        assert sum(budget) == 1000
        assert sorted(budget) == [330, 330, 340]

    def test_all_zero_means_equal_split(self):
        assert allocate_words([0, 0], 600) == [300, 300]

    def test_no_target_keeps_planner_numbers(self):
        assert allocate_words([120, 80], None) == [120, 80]

    def test_small_target_uses_units(self):
        assert sum(allocate_words([3, 1], 90)) == 90

    def test_empty(self):
        assert allocate_words([], 500) == []


class TestHelpers:
    def test_paragraphs(self):
        assert paragraphs(DRAFT) == [p for p in DRAFT.split("\n\n")]

    def test_quote_in_tolerates_case_space_quotes_and_elision(self):
        text = "Teachers use chatbots to   prepare lessons (Tan, 2021)."
        assert quote_in("“teachers use chatbots”", text)
        assert quote_in("Teachers use ... lessons", text)
        assert not quote_in("teachers hate chatbots", text)

    def test_trim_words(self):
        assert trim_words("a b c", 5) == ("a b c", False)
        assert trim_words("a b c d e f", 3) == ("a b c …", True)


async def test_plan_budget_readings_and_two_agents(fake_llm, llm_config):
    fake_llm.responder = router()
    result = await AcademicCrew(llm_config).plan("Write 1500 words on AI in schools.")
    assert [agent_of(c) for c in fake_llm.calls] == ["brief", "planner"]
    assert result.target_words == 1500  # from the brief agent
    assert sum(result.budget) == 1500
    assert result.style == "apa"
    statuses = [r.status for r in result.readings]
    assert statuses == ["unverified", "flagged"]
    assert result.counts() == {
        "research_questions": 2,
        "sections": 4,
        "suggested_readings": 2,
        "flagged_readings": 1,
    }
    assert result.tracker.total_calls == 2


async def test_plan_words_option_overrides_brief(fake_llm, llm_config):
    fake_llm.responder = router()
    result = await AcademicCrew(llm_config).plan("brief", words=800, style="ieee")
    assert sum(result.budget) == 800 and result.style == "ieee"
    assert "800 words" in fake_llm.user_prompt(1) and "IEEE" in fake_llm.user_prompt(1)


async def test_plan_without_outline_fails_naming_planner(fake_llm, llm_config):
    bad = json.loads(PLAN)
    bad["outline"] = []
    fake_llm.responder = router({"planner": json.dumps(bad)})
    with pytest.raises(CrewFailedError) as exc:
        await AcademicCrew(llm_config).plan("brief")
    assert exc.value.agents == ["planner"]


async def test_plan_brief_in_prose_fails_naming_brief(fake_llm, llm_config):
    fake_llm.responder = router({"brief": "Sure! The brief is about AI."})
    with pytest.raises(CrewFailedError) as exc:
        await AcademicCrew(llm_config).plan("brief")
    assert exc.value.agents == ["brief"]
    assert len(fake_llm.calls) == 1  # the planner never ran


async def test_plan_in_malay_sends_instruction_and_checks_output(fake_llm, llm_config):
    plan = json.loads(PLAN)
    plan["research_questions"] = ["Bagaimanakah dosen menggunakan AI karena kualitas?"]
    fake_llm.responder = router({"planner": json.dumps(plan)})
    result = await AcademicCrew(llm_config, language="ms").plan("brief")
    assert "Malaysian Malay" in fake_llm.system_prompt(0)
    assert "Malaysian Malay" in fake_llm.system_prompt(1)
    assert set(result.malay_issues) == {"dosen", "karena", "kualitas"}


async def test_feedback_runs_four_reviewers_and_checks_comments(fake_llm, llm_config):
    comments = [
        {
            "paragraph": 3,
            "quote": "Teachers use chatbots",
            "issue": "wrong para",
            "severity": "high",
        },
        {"paragraph": 9, "quote": "not in the draft", "issue": "invented quote"},
        {"paragraph": 1, "quote": "", "issue": "long", "suggestion": " ".join(["word"] * 80)},
    ]
    fake_llm.responder = router({"argument": feedback_reply(comments)})
    result = await AcademicCrew(llm_config, max_suggestion_words=10).feedback(DRAFT)
    assert sorted(agent_of(c) for c in fake_llm.calls) == [
        "argument",
        "citations",
        "clarity",
        "structure",
    ]
    assert "[P2] Teachers use chatbots" in fake_llm.user_prompt(0)
    by_issue = {c.issue: c for c in result.comments}
    assert by_issue["wrong para"].paragraph == 2 and by_issue["wrong para"].flags == []
    assert by_issue["wrong para"].severity == "major"
    assert by_issue["invented quote"].paragraph is None
    assert by_issue["invented quote"].flags == ["paragraph_out_of_range", "quote_not_found"]
    assert by_issue["long"].flags == ["suggestion_trimmed"]
    assert by_issue["long"].suggestion.endswith("…")
    assert len(by_issue["long"].suggestion.split()) == 11
    assert result.citations.in_text == ["Tan, 2021"]
    assert not result.citations.has_reference_list


async def test_feedback_empty_reviewer_fails_naming_it(fake_llm, llm_config):
    fake_llm.responder = router({"clarity": ""})
    with pytest.raises(CrewFailedError) as exc:
        await AcademicCrew(llm_config).feedback(DRAFT)
    assert exc.value.agents == ["clarity"]


async def test_feedback_reviewer_without_comments_key_fails(fake_llm, llm_config):
    fake_llm.responder = router({"structure": json.dumps({"summary": "fine"})})
    with pytest.raises(CrewFailedError) as exc:
        await AcademicCrew(llm_config).feedback(DRAFT)
    assert exc.value.agents == ["structure"]


async def test_feedback_allow_partial_keeps_going_and_lists_failure(fake_llm, llm_config):
    fake_llm.responder = router({"clarity": httpx.Response(500, json={"error": "boom"})})
    result = await AcademicCrew(llm_config).feedback(DRAFT, allow_partial=True)
    assert set(result.reviews) == {"structure", "argument", "citations"}
    assert "clarity" in result.failed


async def test_feedback_single_reviewer(fake_llm, llm_config):
    fake_llm.responder = router()
    result = await AcademicCrew(llm_config).feedback(DRAFT, reviewers=["citations"])
    assert [agent_of(c) for c in fake_llm.calls] == ["citations"]
    assert list(result.reviews) == ["citations"]


async def test_cite_echo_sorted_apa(fake_llm, llm_config):
    fake_llm.responder = router()
    refs = ["Zainal, A. (2020). Z. https://doi.org/10.1/z", "Ahmad, B. (2019). A."]
    result = await AcademicCrew(llm_config).cite(refs, style="apa")
    assert [r.formatted for r in result.refs] == [refs[1], refs[0]]
    assert [r.check.status for r in result.refs] == ["supplied", "supplied"]
    assert result.discarded == []


async def test_cite_ieee_keeps_input_order(fake_llm, llm_config):
    fake_llm.responder = router()
    refs = ["Zainal, A. Z.", "Ahmad, B. A."]
    result = await AcademicCrew(llm_config).cite(refs, style="ieee")
    assert [r.index for r in result.refs] == [1, 2]


async def test_cite_skipped_reference_fails_naming_formatter(fake_llm, llm_config):
    reply = json.dumps({"references": [{"index": 1, "formatted": "One."}]})
    fake_llm.responder = router({"formatter": reply})
    with pytest.raises(CrewFailedError) as exc:
        await AcademicCrew(llm_config).cite(["one", "two"])
    assert exc.value.agents == ["formatter"]
    assert "skipped supplied reference(s) 2" in str(exc.value)


async def test_cite_extra_reference_is_discarded_and_added_doi_flagged(fake_llm, llm_config):
    reply = json.dumps(
        {
            "references": [
                {"index": 1, "formatted": "Tan, A. (2021). T. https://doi.org/10.5555/invented"},
                {"index": 2, "formatted": "Invented, X. (2020). A source nobody supplied."},
            ]
        }
    )
    fake_llm.responder = router({"formatter": reply})
    result = await AcademicCrew(llm_config).cite(["Tan A 2021 T"])
    assert len(result.refs) == 1
    assert result.refs[0].check.status == "unverified"
    assert "identifier_added_by_ai" in result.refs[0].check.flag_codes
    assert [d.formatted for d in result.discarded] == [
        "Invented, X. (2020). A source nobody supplied."
    ]


async def test_cite_without_references_is_rejected(llm_config):
    with pytest.raises(ValueError):
        await AcademicCrew(llm_config).cite([])
