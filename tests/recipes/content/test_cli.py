"""`crewforge write` honest-failure behaviour (new in crewforge)."""

from __future__ import annotations

from click.testing import CliRunner

from crewforge.cli import main
from tests.recipes.content.fakes import agent_of, router


def _write(tmp_path, *args):
    return CliRunner().invoke(main, ["write", "Unit tests", "-o", str(tmp_path / "o"), *args])


def test_happy_path_writes_files_and_usage(fake_llm, tmp_path):
    fake_llm.responder = router()
    res = _write(tmp_path)
    assert res.exit_code == 0, res.output
    assert (tmp_path / "o" / "unit-tests.md").exists()
    assert (tmp_path / "o" / "unit-tests.publisher.json").exists()
    assert "quality score 90/100" in res.output
    assert "Token usage" in res.output


def test_empty_writer_stops_the_run(fake_llm, tmp_path):
    fake_llm.responder = router({"writer": ""})
    res = _write(tmp_path)
    assert res.exit_code == 1
    assert "agent 'writer'" in res.output
    assert [agent_of(c) for c in fake_llm.calls] == ["research", "outline", "writer"]


def test_prose_quality_fails_without_looping(fake_llm, tmp_path):
    fake_llm.responder = router({"quality": "Looks great, solid 9/10."})
    res = _write(tmp_path, "--max-iter", "3")
    assert res.exit_code == 1
    assert "agent 'quality'" in res.output and "(parse)" in res.output
    assert [agent_of(c) for c in fake_llm.calls].count("editor") == 1


def test_score_below_threshold_fails(fake_llm, tmp_path):
    fake_llm.responder = router({"quality": '{"overall_score": 55}'})
    res = _write(tmp_path, "--max-iter", "2")
    assert res.exit_code == 1
    assert "agent 'quality'" in res.output and "below the threshold 80" in res.output
    assert [agent_of(c) for c in fake_llm.calls].count("editor") == 2
    assert not (tmp_path / "o" / "unit-tests.md").exists()


def test_accept_below_threshold_warns(fake_llm, tmp_path):
    fake_llm.responder = router({"quality": '{"overall_score": 55}'})
    res = _write(tmp_path, "--max-iter", "1", "--accept-below-threshold")
    assert res.exit_code == 0, res.output
    assert "below the threshold" in res.output and "accepted" in res.output


def test_empty_translation_names_language(fake_llm, tmp_path):
    def respond(payload):
        if agent_of(payload) == "translator" and " to ms." in payload["messages"][-1]["content"]:
            return ""
        return router()(payload)

    fake_llm.responder = respond
    res = _write(tmp_path, "-t", "zh", "-t", "ms")
    assert res.exit_code == 1
    assert "agent 'translator_ms'" in res.output
    assert "translator_zh" not in res.output.split("error:")[1]


def test_bad_threshold_is_usage_error(fake_llm, tmp_path):
    res = _write(tmp_path, "--threshold", "80")
    assert res.exit_code == 2 and "quality_threshold" in res.output
    assert fake_llm.calls == []
