"""The root `crewforge` command: version, providers, init, global provider options."""

from __future__ import annotations

import yaml
from click.testing import CliRunner

from crewforge import __version__
from crewforge.cli import main
from crewforge.core.providers import PROVIDERS


def test_version():
    result = CliRunner().invoke(main, ["--version"])
    assert result.exit_code == 0 and __version__ in result.output


def test_help_lists_every_recipe_command():
    out = CliRunner().invoke(main, ["--help"]).output
    for cmd in (
        "review",
        "ingest",
        "ask",
        "summarize",
        "scaffold",
        "validate",
        "write",
        "providers",
    ):
        assert cmd in out


def test_providers_lists_every_preset_and_key_variable():
    result = CliRunner().invoke(main, ["providers"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    for p in PROVIDERS.values():
        assert p.name in result.output
        assert p.env_key in result.output


def test_init_writes_reference_never_the_key(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk-real-secret")
    out = tmp_path / "crewforge.yaml"
    result = CliRunner().invoke(main, ["--provider", "groq", "init", "-o", str(out)])
    assert result.exit_code == 0, result.output
    text = out.read_text()
    assert "gsk-real-secret" not in text
    data = yaml.safe_load(text)
    assert data["llm"]["api_key"] == "${GROQ_API_KEY}"
    assert data["llm"]["provider"] == "groq"


def test_init_refuses_to_overwrite(tmp_path):
    out = tmp_path / "crewforge.yaml"
    out.write_text("keep: me\n")
    result = CliRunner().invoke(main, ["init", "-o", str(out)])
    assert result.exit_code == 2 and out.read_text() == "keep: me\n"


def test_global_options_reach_the_request(fake_llm, tmp_path):
    fake_llm.replies = ["A summary."]
    doc = tmp_path / "d.txt"
    doc.write_text("Some text about pipelines and agents.")
    result = CliRunner().invoke(
        main,
        ["--model", "my-model", "--base-url", "http://gateway.test/v1", "summarize", str(doc)],
    )
    assert result.exit_code == 0, result.output
    assert fake_llm.calls[0]["model"] == "my-model"


def test_config_file_with_env_reference(fake_llm, tmp_path, monkeypatch):
    monkeypatch.setenv("MY_KEY", "sk-from-ref")
    cfg = tmp_path / "c.yaml"
    cfg.write_text("llm:\n  provider: openai\n  model: cfg-model\n  api_key: ${MY_KEY}\n")
    doc = tmp_path / "d.txt"
    doc.write_text("Some text about pipelines.")
    fake_llm.replies = ["Summary."]
    result = CliRunner().invoke(main, ["--config", str(cfg), "summarize", str(doc)])
    assert result.exit_code == 0, result.output
    assert fake_llm.calls[0]["model"] == "cfg-model"


def test_unknown_provider_is_a_usage_error(tmp_path):
    doc = tmp_path / "d.txt"
    doc.write_text("text")
    result = CliRunner().invoke(main, ["--provider", "nope", "summarize", str(doc)])
    assert result.exit_code == 2 and "unknown provider 'nope'" in result.output


def test_switching_provider_drops_the_other_providers_key(fake_llm, tmp_path):
    # OPENAI_API_KEY is set by fake_llm; --provider groq must not reuse it.
    doc = tmp_path / "d.txt"
    doc.write_text("text")
    result = CliRunner().invoke(main, ["--provider", "groq", "summarize", str(doc)])
    assert result.exit_code == 2 and "GROQ_API_KEY" in result.output
    assert fake_llm.calls == []
