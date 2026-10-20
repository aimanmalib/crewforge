"""`crewforge review` end to end through the fake endpoint (ported from codeguard test_cli.py)."""

from __future__ import annotations

import json

import httpx
from click.testing import CliRunner

from crewforge.cli import main
from crewforge.recipes.review.cli import _detect_language
from tests.recipes.review.fakes import router


class TestDetectLanguage:
    def test_python(self):
        assert _detect_language(".py") == "python"

    def test_typescript(self):
        assert _detect_language(".ts") == "typescript"
        assert _detect_language(".tsx") == "typescript"

    def test_case_insensitive(self):
        assert _detect_language(".PY") == "python"

    def test_unknown_extension_returns_auto(self):
        assert _detect_language(".xyz") == "auto"

    def test_go_and_rust(self):
        assert _detect_language(".go") == "go"
        assert _detect_language(".rs") == "rust"


def _invoke(tmp_path, *args):
    src = tmp_path / "a.py"
    src.write_text("x = 1\n")
    return CliRunner().invoke(main, ["review", str(src), *args])


class TestReviewCommand:
    def test_json_report_includes_findings_status_and_summary(self, fake_llm, tmp_path):
        fake_llm.responder = router()
        out = tmp_path / "r.json"
        res = _invoke(tmp_path, "-f", "json", "-o", str(out))
        assert res.exit_code == 0, res.output
        data = json.loads(out.read_text())
        assert data["agents"]["security"]["summary"] == "SQL injection on line 4"
        assert data["agents"]["security"]["findings"][0]["cwe"] == "CWE-89"
        assert data["agents"]["style"]["status"] == "success"
        assert data["decision"] == "REQUEST_CHANGES"
        assert data["summary"]["report"] == "Fix the injection."
        assert data["total_tokens"] == 7 * 15

    def test_markdown_report_shows_agent_output(self, fake_llm, tmp_path):
        # codeguard printed "Agent failed: boom" and exited 0; that is now opt-in.
        fake_llm.responder = router({"style": httpx.Response(500, json={"error": "boom"})})
        res = _invoke(tmp_path, "-f", "markdown", "--allow-partial")
        assert res.exit_code == 0, res.output
        assert "SQL injection" in res.output
        assert "REQUEST_CHANGES" in res.output
        assert "Agent failed: HTTP 500" in res.output and "boom" in res.output
        assert "1 agent(s) failed and were skipped: style" in res.output

    def test_failed_review_exits_nonzero_with_reason(self, fake_llm, tmp_path):
        fake_llm.replies = [httpx.Response(401, json={"error": {"message": "bad key"}})]
        res = _invoke(tmp_path)
        assert res.exit_code == 1
        assert "review failed" in res.output
        assert "OPENAI_API_KEY" in res.output
        assert len(fake_llm.calls) == 6  # one attempt per reviewer, no summary


class TestHonestFailure:
    def test_empty_reviewer_fails_run_naming_agent(self, fake_llm, tmp_path):
        fake_llm.responder = router({"complexity": ""})
        res = _invoke(tmp_path)
        assert res.exit_code == 1
        assert "agent 'complexity'" in res.output and "(empty)" in res.output
        assert not any(
            c["messages"][0]["content"].startswith("You are the summary") for c in fake_llm.calls
        )

    def test_prose_reviewer_fails_run_as_parse_error(self, fake_llm, tmp_path):
        fake_llm.responder = router({"testing": "I would add more tests."})
        res = _invoke(tmp_path, "-f", "json")
        assert res.exit_code == 1
        assert "agent 'testing'" in res.output and "(parse)" in res.output

    def test_empty_summary_fails_run(self, fake_llm, tmp_path):
        fake_llm.responder = router({"summary": "  "})
        res = _invoke(tmp_path)
        assert res.exit_code == 1
        assert "agent 'summary'" in res.output

    def test_no_key_is_a_config_error_before_any_call(self, fake_llm, tmp_path, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY")
        res = _invoke(tmp_path)
        assert res.exit_code == 2
        assert "OPENAI_API_KEY" in res.output
        assert fake_llm.calls == []

    def test_missing_path_and_empty_dir(self, fake_llm, tmp_path):
        res = CliRunner().invoke(main, ["review", str(tmp_path / "nope.py")])
        assert res.exit_code == 2 and "path not found" in res.output
        res = CliRunner().invoke(main, ["review", str(tmp_path)])
        assert res.exit_code == 2 and "no supported source files" in res.output
        assert fake_llm.calls == []

    def test_directory_review_skips_vendored_dirs(self, fake_llm, tmp_path):
        fake_llm.responder = router()
        (tmp_path / "app.py").write_text("print(1)\n")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "lib.js").write_text("var x;\n")
        res = CliRunner().invoke(main, ["review", str(tmp_path), "-f", "json"])
        assert res.exit_code == 0, res.output
        prompt = fake_llm.calls[0]["messages"][-1]["content"]
        assert "# File: app.py" in prompt and "lib.js" not in prompt
