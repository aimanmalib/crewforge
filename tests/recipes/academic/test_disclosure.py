"""The usage record and the AI-use statement generated from it (no LLM)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from crewforge import __version__
from crewforge.core.config import LLMConfig
from crewforge.recipes.academic.disclosure import (
    DisclosureError,
    append_record,
    build_statement,
    make_record,
    read_records,
    summarise,
)

CONFIG = LLMConfig(
    provider="custom", api_key="sk-secret-key", base_url="http://10.0.0.5:9999/v1", model="m-1"
)
DAY1 = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
DAY2 = datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)


def _plan(now=DAY1, readings=2, flagged=1):
    return make_record(
        "plan",
        config=CONFIG,
        language="en",
        inputs=[("/home/student/brief.md", "the brief text")],
        counts={
            "research_questions": 3,
            "sections": 5,
            "suggested_readings": readings,
            "flagged_readings": flagged,
        },
        style="apa",
        tokens=1200,
        now=now,
    )


def _feedback(now=DAY2, comments=7):
    return make_record(
        "feedback",
        config=CONFIG,
        language="en",
        inputs=[("draft.md", "my draft")],
        counts={"comments": comments, "paragraphs": 6},
        style="apa",
        now=now,
    )


def _cite(now=DAY2):
    return make_record(
        "cite",
        config=CONFIG,
        language="en",
        inputs=[("refs.txt", "refs")],
        counts={"references": 4, "discarded": 0},
        style="ieee",
        now=now,
    )


class TestRecord:
    def test_record_holds_what_happened_but_no_secret_url_or_content(self):
        rec = _plan()
        text = json.dumps(rec)
        assert "sk-secret-key" not in text
        assert "10.0.0.5" not in text and "9999" not in text
        assert "the brief text" not in text
        assert "/home/student" not in text  # file name only
        assert rec["inputs"][0]["name"] == "brief.md"
        assert len(rec["inputs"][0]["sha256"]) == 64
        assert rec["model"] == "m-1" and rec["provider"] == "custom"
        assert rec["version"] == __version__

    def test_unknown_step_is_rejected(self):
        with pytest.raises(ValueError):
            make_record("humanize", config=CONFIG, language="en", inputs=[], counts={})

    def test_append_and_read_back(self, tmp_path):
        log = tmp_path / "sub" / "log.jsonl"
        append_record(log, _plan())
        append_record(log, _feedback())
        assert [r["step"] for r in read_records(log)] == ["plan", "feedback"]

    def test_corrupt_line_is_an_error_naming_the_line(self, tmp_path):
        log = tmp_path / "log.jsonl"
        log.write_text(json.dumps(_plan()) + "\n{not json\n")
        with pytest.raises(DisclosureError, match=r"log\.jsonl:2"):
            read_records(log)

    def test_foreign_json_is_rejected(self, tmp_path):
        log = tmp_path / "log.jsonl"
        log.write_text('{"step": "essay", "ts": "2026-10-20T00:00:00+00:00"}\n')
        with pytest.raises(DisclosureError, match="not a crewforge academic usage record"):
            read_records(log)


class TestStatement:
    def test_english_statement_lists_each_step_with_counts(self):
        text = build_statement([_plan(), _feedback(), _cite()], "en")
        assert text.startswith("## AI-use statement")
        assert f"crewforge academic (version {__version__})" in text
        assert "m-1 (custom)" in text
        assert (
            "- 20 October 2026: Planning: the tool turned the assignment brief (brief.md) into 3"
            in text
        )
        assert "It proposed 2 reading(s), labelled as unverified. 1 of them had no DOI" in text
        assert "(7 comment(s)). It did not rewrite the draft." in text
        assert "formatted 4 reference(s) that I supplied (refs.txt) into IEEE style" in text
        assert "- [ ] I checked that every source" in text
        # Order follows the workflow, not the log order.
        assert text.index("Planning") < text.index("Feedback") < text.index("Reference formatting")

    def test_malay_statement(self):
        text = build_statement([_plan(), _feedback(), _cite()], "ms")
        assert text.startswith("## Pernyataan Penggunaan AI")
        assert "- 20 Oktober 2026: Perancangan:" in text
        assert "(7 ulasan). Alat ini tidak menulis semula draf tersebut." in text
        assert "mengikut gaya IEEE" in text
        assert "- [ ] Saya telah menyemak" in text

    def test_steps_that_did_not_happen_are_not_claimed(self):
        text = build_statement([_feedback()], "en")
        assert "Planning" not in text and "Reference formatting" not in text

    def test_plan_without_readings_does_not_mention_them(self):
        text = build_statement([_plan(readings=0, flagged=0)], "en")
        assert "proposed" not in text

    def test_unflagged_readings_do_not_mention_fabrication(self):
        text = build_statement([_plan(readings=3, flagged=0)], "en")
        assert "proposed 3 reading(s)" in text and "fabricated" not in text

    def test_repeated_runs_are_merged(self):
        steps = summarise([_feedback(DAY1, 3), _feedback(DAY2, 4)])
        assert len(steps) == 1
        assert steps[0].counts["comments"] == 7 and steps[0].runs == 2
        text = build_statement([_feedback(DAY1, 3), _feedback(DAY2, 4)], "en")
        assert "- 20 October 2026, 22 October 2026: Feedback" in text

    def test_no_records_is_an_error(self):
        with pytest.raises(DisclosureError):
            build_statement([], "en")
