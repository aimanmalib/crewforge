"""`crewforge review -f sarif`: SARIF 2.1.0 for GitHub code scanning (issue #3)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from click.testing import CliRunner

from crewforge import __version__
from crewforge.cli import main
from crewforge.recipes.review.agents import AgentResult
from crewforge.recipes.review.pipeline import ReviewResult
from crewforge.recipes.review.report import report_sarif
from crewforge.recipes.review.sources import collect
from tests.recipes.review.fakes import router


def _result(*findings: dict, failed: str | None = None) -> ReviewResult:
    agents = {"security": AgentResult("security", findings=list(findings))}
    if failed:
        agents[failed] = AgentResult(failed, status="failed", error="HTTP 500")
    return ReviewResult(agent_results=agents)


def _sarif(tmp_path: Path, *args: str):
    src = tmp_path / "a.py"
    src.write_text('import sqlite3\n\ndef find(conn, name):\n    return conn.execute(f"{name}")\n')
    out = tmp_path / "r.sarif"
    res = CliRunner().invoke(main, ["review", str(src), "-f", "sarif", "-o", str(out), *args])
    return res, src, out


class TestCli:
    def test_single_file_report_is_sarif_with_one_result_per_finding(self, fake_llm, tmp_path):
        fake_llm.responder = router()
        res, src, out = _sarif(tmp_path)
        assert res.exit_code == 0, res.output
        log = json.loads(out.read_text())
        assert log["version"] == "2.1.0"
        assert log["$schema"].endswith("sarif-2.1.0.json")
        run = log["runs"][0]
        assert run["tool"]["driver"]["name"] == "crewforge"
        assert run["tool"]["driver"]["version"] == __version__
        assert run["invocations"][0]["executionSuccessful"] is True
        # The fake security reviewer reports one critical CWE-89 on line 4; the rest are clean.
        [only] = run["results"]
        assert only["ruleId"] == "CWE-89"
        assert only["level"] == "error"
        assert only["message"]["text"] == "SQL injection: query built with f-string"
        loc = only["locations"][0]["physicalLocation"]
        assert loc["artifactLocation"]["uri"] == src.as_uri()
        assert loc["region"] == {"startLine": 4}
        assert {"id": "CWE-89"} in run["tool"]["driver"]["rules"]

    def test_failed_reviewer_still_exits_1(self, fake_llm, tmp_path):
        fake_llm.responder = router({"style": httpx.Response(500, json={"error": "boom"})})
        res, _, out = _sarif(tmp_path)
        assert res.exit_code == 1
        assert "agent 'style'" in res.output
        assert not out.exists()

    def test_allow_partial_marks_the_run_unsuccessful_and_names_the_agent(self, fake_llm, tmp_path):
        fake_llm.responder = router({"style": httpx.Response(500, json={"error": "boom"})})
        res, _, out = _sarif(tmp_path, "--allow-partial")
        assert res.exit_code == 0, res.output
        inv = json.loads(out.read_text())["runs"][0]["invocations"][0]
        assert inv["executionSuccessful"] is False
        [note] = inv["toolExecutionNotifications"]
        assert note["message"]["text"].startswith("agent 'style' failed")

    def test_sarif_to_stdout_is_plain_json(self, fake_llm, tmp_path):
        fake_llm.responder = router()
        src = tmp_path / "a.py"
        src.write_text("x = 1\n")
        res = CliRunner().invoke(main, ["review", str(src), "-f", "sarif"])
        assert res.exit_code == 0, res.output
        start = res.output.index("{\n")
        log, _ = json.JSONDecoder().raw_decode(res.output[start:])
        assert log["version"] == "2.1.0"


class TestReport:
    @pytest.mark.parametrize(
        ("severity", "level"),
        [("critical", "error"), ("error", "error"), ("warning", "warning"), ("info", "note")],
    )
    def test_severity_maps_to_level(self, tmp_path, severity, level):
        src = tmp_path / "a.py"
        src.write_text("x = 1\n")
        log = report_sarif(_result({"severity": severity, "title": "t"}), collect(src), src)
        assert log["runs"][0]["results"][0]["level"] == level

    def test_rule_is_the_agent_without_a_cwe_and_fix_is_in_the_message(self, tmp_path):
        src = tmp_path / "a.py"
        src.write_text("x = 1\n")
        finding = {"severity": "warning", "title": "", "suggestion": "rename it"}
        [r] = report_sarif(_result(finding), collect(src), src)["runs"][0]["results"]
        assert r["ruleId"] == "security"
        assert r["message"]["text"] == "Untitled\nFix: rename it"

    @pytest.mark.parametrize("line", [None, "", "4-6", 0, -1, True, "abc", 99])
    def test_line_that_is_not_a_line_of_the_file_has_no_region(self, tmp_path, line):
        src = tmp_path / "a.py"
        src.write_text("x = 1\ny = 2\n")
        log = report_sarif(_result({"title": "t", "line": line}), collect(src), src)
        loc = log["runs"][0]["results"][0]["locations"][0]["physicalLocation"]
        assert loc == {"artifactLocation": {"uri": src.as_uri()}}

    def test_relative_paths_stay_relative(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        Path("src").mkdir()
        Path("src/a.py").write_text("x = 1\ny = 2\n")
        log = report_sarif(_result({"title": "t", "line": "2"}), collect("src/a.py"), "src/a.py")
        loc = log["runs"][0]["results"][0]["locations"][0]["physicalLocation"]
        assert loc == {"artifactLocation": {"uri": "src/a.py"}, "region": {"startLine": 2}}


class TestDirectoryLines:
    """In a directory review the line refers to the joined text; map it back to the file."""

    def _tree(self, root: Path) -> None:
        (root / "pkg").mkdir()
        (root / "a.py").write_text("a1 = 1\na2 = 2\n")
        (root / "pkg" / "b.py").write_text("b1 = 1\nb2 = 2\nb3 = 3")  # no final newline
        (root / "c.py").write_text("c1 = 1\n")

    def test_every_code_line_maps_to_the_same_text_in_its_file(self, tmp_path):
        self._tree(tmp_path)
        sources = collect(tmp_path)
        mapped = 0
        for n, text in enumerate(sources.code.split("\n"), start=1):
            spot = sources.locate(n)
            if text.startswith("# File:") or text == "":
                assert spot is None, (n, text)
                continue
            path, line = spot  # type: ignore[misc]
            assert path.read_text().split("\n")[line - 1] == text
            mapped += 1
        assert mapped == 6

    def test_finding_in_second_file_points_at_that_file(self, tmp_path):
        self._tree(tmp_path)
        sources = collect(tmp_path)
        n = sources.code.split("\n").index("b2 = 2") + 1
        log = report_sarif(_result({"title": "t", "line": n}), sources, tmp_path)
        loc = log["runs"][0]["results"][0]["locations"][0]["physicalLocation"]
        assert loc == {
            "artifactLocation": {"uri": (tmp_path / "pkg" / "b.py").as_uri()},
            "region": {"startLine": 2},
        }

    def test_finding_on_a_header_keeps_the_directory_without_region(self, tmp_path):
        self._tree(tmp_path)
        log = report_sarif(_result({"title": "t", "line": 1}), collect(tmp_path), tmp_path)
        loc = log["runs"][0]["results"][0]["locations"][0]["physicalLocation"]
        assert loc == {"artifactLocation": {"uri": tmp_path.as_uri()}}
