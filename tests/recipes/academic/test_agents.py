"""Agent output schemas: tolerant of real-model quirks, strict about what matters."""

from __future__ import annotations

import pytest

from crewforge.core.errors import OutputParseError
from crewforge.core.parsing import parse_json
from crewforge.recipes.academic.agents import (
    FEEDBACK_AGENTS,
    BriefInfo,
    CiteOutput,
    Comment,
    FeedbackOutput,
    FormattedRef,
    PlannerAgent,
    PlanOutput,
    Section,
)


class TestBriefInfo:
    def test_normalises_real_model_values(self):
        b = BriefInfo.model_validate(
            {
                "title": "  AI in schools ",
                "word_count": "1,500 words",
                "citation_style": "APA 7th edition",
                "rubric": [{"criterion": "Analysis", "weight": "30%"}],
                "requirements": "Five sources",
            }
        )
        assert b.title == "AI in schools"
        assert b.word_count == 1500
        assert b.citation_style == "apa"
        assert b.rubric[0].weight == 30.0
        assert b.requirements == ["Five sources"]

    @pytest.mark.parametrize("style, expected", [("MLA", None), ("ieee", "ieee"), (None, None)])
    def test_unsupported_style_becomes_none(self, style, expected):
        assert BriefInfo(title="x", citation_style=style).citation_style == expected

    def test_missing_title_fails_naming_agent(self):
        with pytest.raises(OutputParseError, match="agent 'brief'"):
            parse_json('{"title": "  "}', agent="brief", schema=BriefInfo)


class TestPlanOutput:
    def test_needs_questions_and_outline(self):
        with pytest.raises(OutputParseError, match="research_questions"):
            parse_json(
                '{"research_questions": [], "outline": [{"heading": "x"}]}',
                agent="planner",
                schema=PlanOutput,
            )
        with pytest.raises(OutputParseError, match="outline"):
            parse_json('{"research_questions": ["q"]}', agent="planner", schema=PlanOutput)

    @pytest.mark.parametrize(
        "raw, clean",
        [
            ("1. Introduction", "Introduction"),
            ("2.1 Background", "Background"),
            ("3) Method", "Method"),
            ("IV. Discussion", "Discussion"),
            ("2020 election results", "2020 election results"),
        ],
    )
    def test_model_numbering_is_removed_from_headings(self, raw, clean):
        assert Section(heading=raw).heading == clean

    def test_words_tolerates_strings(self):
        assert Section(heading="x", words="1,200").words == 1200
        assert Section(heading="x", words="about").words == 0


class TestFeedback:
    def test_comments_key_is_required(self):
        with pytest.raises(OutputParseError):
            parse_json('{"summary": "fine"}', agent="clarity", schema=FeedbackOutput)

    def test_empty_comments_is_valid(self):
        assert parse_json('{"comments": []}', agent="clarity", schema=FeedbackOutput).comments == []

    def test_comment_normalisation(self):
        c = Comment(paragraph="P3", issue="x", severity="High")
        assert c.paragraph == 3 and c.severity == "major"
        assert Comment(issue="x", severity="nit").severity == "minor"

    def test_comment_without_issue_is_rejected(self):
        with pytest.raises(ValueError):
            Comment(issue=" ")

    def test_reviewers_comment_and_never_rewrite(self):
        assert list(FEEDBACK_AGENTS) == ["structure", "argument", "clarity", "citations"]
        for cls in FEEDBACK_AGENTS.values():
            prompt = cls.build_system_prompt("en")
            assert "do NOT rewrite" in prompt
            assert "Malaysian Malay" in cls.build_system_prompt("ms")


class TestFormatter:
    def test_model_numbering_and_html_italics_are_cleaned(self):
        ref = FormattedRef(index=1, formatted="[1] W. Holmes, <em>AI in Education</em>. CCR, 2019.")
        assert ref.formatted == "W. Holmes, *AI in Education*. CCR, 2019."
        assert FormattedRef(index=2, formatted="2. <i>Book</i>").formatted == "*Book*"

    def test_at_least_one_reference(self):
        with pytest.raises(OutputParseError):
            parse_json('{"references": []}', agent="formatter", schema=CiteOutput)


def test_planner_is_told_not_to_write_or_invent():
    prompt = PlannerAgent.system_prompt
    assert "never write the assignment" in prompt
    assert "never invent a reference" in prompt
