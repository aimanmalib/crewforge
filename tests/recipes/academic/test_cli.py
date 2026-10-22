"""`crewforge academic ...` end to end through the fake endpoint."""

from __future__ import annotations

import json

from click.testing import CliRunner

from crewforge.cli import main
from tests.recipes.academic.fakes import feedback_reply, router

BRIEF = "Write a 1500-word essay on AI in Malaysian schools. Use APA 7th.\n"
DRAFT = (
    "AI helps teachers (Tan, 2021).\n\nRural schools lack devices.\n\n"
    "References\n\nTan, A. (2021). T.\n"
)


def _files(tmp_path):
    (tmp_path / "brief.md").write_text(BRIEF)
    (tmp_path / "draft.md").write_text(DRAFT)
    (tmp_path / "refs.txt").write_text(
        "Tan A (2021) Teaching with AI. Journal X 3(1).\nLee B 2020 Book. ISBN 978-0-306-40615-7\n"
    )
    return tmp_path


def _run(tmp_path, *args):
    return CliRunner().invoke(
        main, ["academic", *args], catch_exceptions=False, env={"COLUMNS": "200"}
    )


def test_help_lists_subcommands():
    out = CliRunner().invoke(main, ["academic", "--help"]).output
    for cmd in ("plan", "feedback", "cite", "disclose"):
        assert cmd in out
    assert "academic" in CliRunner().invoke(main, ["--help"]).output


def test_full_workflow_then_disclose(fake_llm, tmp_path, monkeypatch):
    monkeypatch.chdir(_files(tmp_path))
    fake_llm.responder = router()
    res = _run(tmp_path, "plan", "brief.md", "-f", "json", "-o", "plan.json")
    assert res.exit_code == 0, res.output
    plan = json.loads((tmp_path / "plan.json").read_text())
    assert plan["budget_total"] == 1500
    assert [r["status"] for r in plan["suggested_readings"]] == ["unverified", "flagged"]

    res = _run(tmp_path, "feedback", "draft.md", "--brief", "brief.md", "-f", "markdown")
    assert res.exit_code == 0, res.output
    assert "# Feedback on draft.md" in res.output
    assert "Citation check (no AI)" in res.output

    res = _run(tmp_path, "cite", "refs.txt", "--style", "ieee", "-f", "markdown")
    assert res.exit_code == 0, res.output
    assert "[1] Tan A (2021)" in res.output and "[2] Lee B 2020" in res.output

    log = tmp_path / "crewforge-academic-log.jsonl"
    assert [json.loads(line)["step"] for line in log.read_text().splitlines()] == [
        "plan",
        "feedback",
        "cite",
    ]
    assert "sk-test" not in log.read_text()

    res = _run(tmp_path, "disclose")
    assert res.exit_code == 0, res.output
    assert "## AI-use statement" in res.output
    assert "Planning" in res.output and "Feedback" in res.output and "IEEE" in res.output
    assert fake_llm.calls  # disclose itself made no call:
    calls = len(fake_llm.calls)
    _run(tmp_path, "disclose", "-L", "ms")
    assert len(fake_llm.calls) == calls


def test_plan_text_output_in_malay(fake_llm, tmp_path, monkeypatch):
    monkeypatch.chdir(_files(tmp_path))
    fake_llm.responder = router()
    res = _run(tmp_path, "plan", "brief.md", "--language", "ms", "--no-log")
    assert res.exit_code == 0, res.output
    assert "Soalan kajian" in res.output
    assert "BELUM DISAHKAN" in res.output and "KEMUNGKINAN REKAAN" in res.output
    assert not (tmp_path / "crewforge-academic-log.jsonl").exists()


def test_flagged_reading_is_never_presented_as_verified(fake_llm, tmp_path, monkeypatch):
    monkeypatch.chdir(_files(tmp_path))
    fake_llm.responder = router()
    res = _run(tmp_path, "plan", "brief.md", "-f", "markdown", "--no-log")
    out = res.output
    assert "Suggested readings (UNVERIFIED)" in out
    assert "LIKELY FABRICATED" in out
    assert "Tan, A. (2022). AI in Malaysian classrooms" in out


def test_empty_reviewer_fails_the_run_naming_it(fake_llm, tmp_path, monkeypatch):
    monkeypatch.chdir(_files(tmp_path))
    fake_llm.responder = router({"argument": "   "})
    res = _run(tmp_path, "feedback", "draft.md")
    assert res.exit_code == 1
    assert "agent 'argument'" in res.output and "(empty)" in res.output
    assert not (tmp_path / "crewforge-academic-log.jsonl").exists()  # failed runs are not recorded


def test_planner_prose_fails_the_run(fake_llm, tmp_path, monkeypatch):
    monkeypatch.chdir(_files(tmp_path))
    fake_llm.responder = router({"planner": "Here is a lovely plan for you!"})
    res = _run(tmp_path, "plan", "brief.md")
    assert res.exit_code == 1
    assert "agent 'planner'" in res.output and "(parse)" in res.output


def test_feedback_json_has_comments_and_flags(fake_llm, tmp_path, monkeypatch):
    monkeypatch.chdir(_files(tmp_path))
    comments = [{"paragraph": 2, "quote": "lack devices", "issue": "needs a citation"}]
    fake_llm.responder = router({"citations": feedback_reply(comments)})
    res = _run(
        tmp_path, "feedback", "draft.md", "-f", "json", "--reviewer", "citations", "-o", "f.json"
    )
    assert res.exit_code == 0, res.output
    data = json.loads((tmp_path / "f.json").read_text())
    assert data["comments"][0]["paragraph"] == 2
    assert data["citation_check"]["in_text"] == ["Tan, 2021"]
    assert data["citation_check"]["cited_not_listed"] == []


def test_disclose_without_log_fails_and_claims_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res = _run(tmp_path, "disclose")
    assert res.exit_code == 1
    assert "No recorded AI use was found" in res.output
    assert "AI-use statement" not in res.output


def test_disclose_empty_log_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "crewforge-academic-log.jsonl").write_text("\n")
    res = _run(tmp_path, "disclose", "-L", "ms")
    assert res.exit_code == 1
    assert "Tiada rekod penggunaan AI" in res.output


def test_disclose_corrupt_log_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "crewforge-academic-log.jsonl").write_text("garbage\n")
    res = _run(tmp_path, "disclose")
    assert res.exit_code == 1 and "not a JSON record" in res.output


def test_too_long_input_is_a_usage_error(fake_llm, tmp_path, monkeypatch):
    monkeypatch.chdir(_files(tmp_path))
    cfg = tmp_path / "c.yaml"
    cfg.write_text("academic:\n  max_input_chars: 10\n")
    res = CliRunner().invoke(main, ["--config", str(cfg), "academic", "plan", "brief.md"])
    assert res.exit_code == 2
    assert "academic.max_input_chars" in res.output
    assert fake_llm.calls == []


def test_config_section_sets_defaults(fake_llm, tmp_path, monkeypatch):
    monkeypatch.chdir(_files(tmp_path))
    cfg = tmp_path / "c.yaml"
    cfg.write_text(
        "academic:\n  language: ms\n  citation_style: harvard\n  log_file: logs/a.jsonl\n"
    )
    fake_llm.responder = router()
    res = CliRunner().invoke(
        main, ["--config", str(cfg), "academic", "cite", "refs.txt", "-f", "markdown"]
    )
    assert res.exit_code == 0, res.output
    assert "Rujukan (Harvard)" in res.output
    assert (tmp_path / "logs" / "a.jsonl").exists()


def test_bad_config_value_is_a_usage_error(tmp_path, monkeypatch):
    monkeypatch.chdir(_files(tmp_path))
    cfg = tmp_path / "c.yaml"
    cfg.write_text("academic:\n  language: id\n")
    res = CliRunner().invoke(main, ["--config", str(cfg), "academic", "disclose"])
    assert res.exit_code == 2 and "academic.language" in res.output


def test_empty_references_file_is_a_usage_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "refs.txt").write_text("References\n")
    res = _run(tmp_path, "cite", "refs.txt")
    assert res.exit_code == 2 and "no references found" in res.output


def test_missing_key_is_a_usage_error(tmp_path, monkeypatch):
    monkeypatch.chdir(_files(tmp_path))
    res = _run(tmp_path, "plan", "brief.md")
    assert res.exit_code == 2 and "OPENAI_API_KEY" in res.output
