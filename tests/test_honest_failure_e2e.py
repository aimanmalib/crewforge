"""Every recipe, end to end: an agent that returns nothing fails the run by name.

This is the user-facing contract of honest failure: exit code 1, the agent
named on stderr, and nothing claimed as a result.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from crewforge.cli import main


@pytest.fixture
def workdir(tmp_path):
    (tmp_path / "app.py").write_text("def add(a, b):\n    return a + b\n")
    (tmp_path / "notes.md").write_text("# Notes\n\nThe pipeline uses four agents.\n")
    return tmp_path


CASES = {
    "review": (["review", "{d}/app.py"], "security"),
    "ask": (["ask", "{d}/notes.md", "-q", "What does the pipeline use?"], "answerer"),
    "summarize": (["summarize", "{d}/notes.md"], "summarizer"),
    "scaffold": (["scaffold", "todo api", "-o", "{d}/out"], "parser"),
    "write": (["write", "unit tests", "-o", "{d}/out"], "research"),
}


@pytest.mark.parametrize("recipe", list(CASES))
def test_blank_reply_fails_the_run_naming_the_agent(fake_llm, workdir, recipe):
    args, first_agent = CASES[recipe]
    fake_llm.replies = [""]
    result = CliRunner().invoke(main, [a.format(d=workdir) for a in args])
    assert result.exit_code == 1, result.output
    assert f"agent '{first_agent}'" in result.output
    assert "returned empty output" in result.output


@pytest.mark.parametrize("recipe", ["review", "scaffold", "write"])
def test_reply_without_required_structure_fails(fake_llm, workdir, recipe):
    # review needs findings JSON, scaffold needs the spec JSON, write's quality
    # needs a score: prose everywhere must fail, never pass as a result.
    args, _ = CASES[recipe]
    fake_llm.replies = ["I'm happy to help with that! " * 3]
    result = CliRunner().invoke(main, [a.format(d=workdir) for a in args])
    assert result.exit_code == 1, result.output
    assert "(parse)" in result.output


def test_success_path_still_exits_zero(fake_llm, workdir):
    fake_llm.replies = [json.dumps({"summary": "fine", "findings": []})] * 6 + [
        json.dumps({"decision": "APPROVE", "quality_score": 95, "summary": "ok"})
    ]
    result = CliRunner().invoke(main, ["review", str(workdir / "app.py"), "-f", "json"])
    assert result.exit_code == 0, result.output
