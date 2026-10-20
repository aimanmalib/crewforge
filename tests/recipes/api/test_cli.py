"""`crewforge scaffold | validate` (ported from apiforge tests/test_cli.py, plus failure tests)."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from crewforge.cli import main
from tests.recipes.api.fakes import agent_of, py, router

VALID = {
    "openapi": "3.1.0",
    "info": {"title": "T", "version": "1"},
    "paths": {"/x": {"get": {"summary": "x", "responses": {"200": {"description": "ok"}}}}},
}


def _scaffold(tmp_path, *args):
    return CliRunner().invoke(main, ["scaffold", "Todo API", "-o", str(tmp_path / "out"), *args])


class TestCLI:
    def test_help(self):
        r = CliRunner().invoke(main, ["--help"])
        assert r.exit_code == 0 and "scaffold" in r.output and "validate" in r.output

    def test_generate_help(self):
        assert CliRunner().invoke(main, ["scaffold", "--help"]).exit_code == 0

    def test_generate_without_key_fails_cleanly(self, tmp_path):
        r = _scaffold(tmp_path)
        assert r.exit_code == 2
        assert "OPENAI_API_KEY" in r.output

    def test_generate_writes_valid_json_spec(self, fake_llm, tmp_path):
        fake_llm.responder = router()
        r = _scaffold(tmp_path)
        assert r.exit_code == 0, r.output
        out = tmp_path / "out"
        spec = json.loads((out / "openapi.json").read_text())
        assert set(spec["paths"]) == {"/todos", "/todos/{id}"}
        assert "Validation: valid" in r.output and "Token usage" in r.output
        for name in ("main.py", "routes.py", "models.py", "auth.py", "tests/test_api.py"):
            compile((out / name).read_text(), name, "exec")
        assert "OPENAI" not in (out / ".env.example").read_text()
        r = CliRunner().invoke(main, ["validate", str(out / "openapi.json")])
        assert r.exit_code == 0 and "Invalid JSON" not in r.output


class TestScaffoldFailures:
    def test_prose_parser_fails_before_other_agents(self, fake_llm, tmp_path):
        fake_llm.responder = router({"parser": "Sure, a todo API sounds great!"})
        r = _scaffold(tmp_path)
        assert r.exit_code == 1 and "agent 'parser'" in r.output and "(parse)" in r.output
        assert [agent_of(c) for c in fake_llm.calls] == ["parser"]
        assert not (tmp_path / "out").exists()

    def test_zero_endpoints_fails_naming_parser(self, fake_llm, tmp_path):
        fake_llm.responder = router({"parser": '{"title": "Todo", "endpoints": []}'})
        r = _scaffold(tmp_path)
        assert r.exit_code == 1 and "agent 'parser'" in r.output and "no endpoints" in r.output

    def test_empty_generation_agent_fails_naming_it(self, fake_llm, tmp_path):
        fake_llm.responder = router({"doc_gen": ""})
        r = _scaffold(tmp_path)
        assert r.exit_code == 1 and "agent 'doc_gen'" in r.output

    def test_non_compiling_router_fails(self, fake_llm, tmp_path):
        fake_llm.responder = router({"router": py("def broken(:\n  pass")})
        r = _scaffold(tmp_path)
        assert r.exit_code == 1 and "agent 'router'" in r.output and "compile" in r.output

    def test_refuses_non_empty_output_dir(self, fake_llm, tmp_path):
        (tmp_path / "out").mkdir()
        (tmp_path / "out" / "keep.txt").write_text("x")
        r = _scaffold(tmp_path)
        assert r.exit_code == 2 and "--force" in r.output
        assert fake_llm.calls == []


class TestValidate:
    def test_valid_spec_file(self, tmp_path):
        p = tmp_path / "s.json"
        p.write_text(json.dumps(VALID))
        r = CliRunner().invoke(main, ["validate", str(p), "--json"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert data["ok"] and data["score"] == 100 and data["operations_checked"] == 1

    def test_empty_paths_fails(self, tmp_path):
        p = tmp_path / "s.json"
        p.write_text(json.dumps({**VALID, "paths": {}}))
        r = CliRunner().invoke(main, ["validate", str(p)])
        assert r.exit_code == 1 and "No endpoints" in r.output and "0/100" in r.output

    def test_paths_without_operations_score_nothing(self, tmp_path):
        p = tmp_path / "s.json"
        p.write_text(json.dumps({**VALID, "paths": {"/x": {"parameters": []}}}))
        r = CliRunner().invoke(main, ["validate", str(p), "--json"])
        assert r.exit_code == 1
        data = json.loads(r.output)
        assert data["score"] == 0 and data["operations_checked"] == 0

    def test_invalid_json_fails(self, tmp_path):
        p = tmp_path / "s.json"
        p.write_text("{not json")
        r = CliRunner().invoke(main, ["validate", str(p)])
        assert r.exit_code == 1 and "not valid JSON" in r.output

    def test_validate_needs_no_key(self, tmp_path):
        p = tmp_path / "s.json"
        p.write_text(json.dumps(VALID))
        assert CliRunner().invoke(main, ["validate", str(p)]).exit_code == 0

    def test_scaffolded_dir_passes_app_check(self, fake_llm, tmp_path):
        pytest.importorskip("fastapi")
        fake_llm.responder = router()
        assert _scaffold(tmp_path).exit_code == 0
        r = CliRunner().invoke(main, ["validate", str(tmp_path / "out"), "--json"])
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data["app_check"]["ran"] and data["app_check"]["errors"] == []

    def test_app_missing_a_spec_route_fails(self, fake_llm, tmp_path):
        pytest.importorskip("fastapi")
        fake_llm.responder = router()
        assert _scaffold(tmp_path).exit_code == 0
        routes = tmp_path / "out" / "routes.py"
        routes.write_text(routes.read_text().replace('@router.delete("/todos/{id}")', ""))
        r = CliRunner().invoke(main, ["validate", str(tmp_path / "out")])
        assert r.exit_code == 1
        assert "DELETE /api/v1/todos/{id} is not served" in r.output

    def test_router_that_drops_a_route_fails_scaffold(self, fake_llm, tmp_path):
        pytest.importorskip("fastapi")
        code = (
            "from fastapi import APIRouter\n"
            'router = APIRouter(prefix="/api/v1")\n\n'
            '@router.get("/todos")\nasync def get_todos():\n    return []\n'
        )
        fake_llm.responder = router({"router": py(code)})
        r = _scaffold(tmp_path)
        assert r.exit_code == 1
        assert "agent 'router'" in r.output and "POST /api/v1/todos" in r.output
