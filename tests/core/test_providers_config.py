"""Provider presets, env resolution and secret handling."""

from __future__ import annotations

import pytest
import yaml

from crewforge.core.config import LLMConfig, Settings, expand_env
from crewforge.core.errors import ConfigError
from crewforge.core.providers import DEFAULT_PROVIDER, PROVIDERS, get_provider

EXPECTED = {
    "openai",
    "openrouter",
    "groq",
    "deepseek",
    "together",
    "mistral",
    "ollama",
    "llamacpp",
    "mimo",
    "custom",
}


def test_all_documented_presets_exist():
    assert set(PROVIDERS) == EXPECTED


def test_default_provider_is_openai():
    assert DEFAULT_PROVIDER == "openai"
    cfg = LLMConfig(api_key="k")
    assert cfg.provider == "openai"
    assert cfg.base_url == "https://api.openai.com/v1"
    assert cfg.model == "gpt-4o-mini"


@pytest.mark.parametrize("name", sorted(EXPECTED - {"custom"}))
def test_every_preset_resolves_url_model_and_auth(name):
    cfg = LLMConfig(provider=name, api_key="k")
    preset = PROVIDERS[name]
    assert cfg.base_url == preset.base_url
    assert cfg.base_url.startswith(("https://", "http://localhost"))
    assert cfg.model == preset.default_model
    assert cfg.auth_style in ("bearer", "api-key")


def test_get_provider_is_case_insensitive():
    assert get_provider("OpenRouter") is PROVIDERS["openrouter"]
    assert get_provider("nope") is None


def test_mimo_uses_api_key_header_everyone_else_bearer():
    assert LLMConfig(provider="mimo", api_key="m").headers["api-key"] == "m"
    assert "Authorization" not in LLMConfig(provider="mimo", api_key="m").headers
    groq = LLMConfig(provider="groq", api_key="g").headers
    assert groq["Authorization"] == "Bearer g"
    assert "api-key" not in groq


def test_keyless_local_provider_sends_no_auth_header():
    headers = LLMConfig(provider="ollama").headers
    assert "Authorization" not in headers and "api-key" not in headers


def test_preset_env_vars(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://proxy.example/v1/")
    cfg = LLMConfig(provider="openrouter")
    assert cfg.api_key == "or-key"
    assert cfg.base_url == "https://proxy.example/v1"  # trailing slash stripped


def test_generic_env_vars_override_preset(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "preset-key")
    monkeypatch.setenv("CREWFORGE_API_KEY", "generic-key")
    monkeypatch.setenv("CREWFORGE_MODEL", "my-model")
    monkeypatch.setenv("CREWFORGE_PROVIDER", "openai")
    cfg = LLMConfig()
    assert cfg.api_key == "generic-key"
    assert cfg.model == "my-model"


def test_explicit_values_beat_env(monkeypatch):
    monkeypatch.setenv("CREWFORGE_MODEL", "env-model")
    cfg = LLMConfig(model="explicit", base_url="http://x/v1", api_key="k")
    assert (cfg.model, cfg.base_url) == ("explicit", "http://x/v1")


def test_custom_requires_base_url_and_model():
    problems = LLMConfig(provider="custom").validate_config()
    assert any("base URL" in p for p in problems)
    assert any("model" in p for p in problems)
    ok = LLMConfig(provider="custom", base_url="http://127.0.0.1:9/v1", model="m")
    assert ok.validate_config() == []  # custom servers may be keyless


def test_unknown_provider_is_reported_not_silently_remapped():
    cfg = LLMConfig(provider="does-not-exist", api_key="k")
    assert any("unknown provider" in p for p in cfg.validate_config())
    with pytest.raises(ConfigError, match="unknown provider"):
        cfg.require_valid()


def test_missing_key_names_the_env_var():
    with pytest.raises(ConfigError, match="DEEPSEEK_API_KEY"):
        LLMConfig(provider="deepseek").require_valid()


def test_key_never_appears_in_repr():
    cfg = LLMConfig(api_key="sk-supersecret")
    assert "sk-supersecret" not in repr(cfg)
    assert "sk-supersecret" not in str(cfg)


def test_template_writes_env_reference_not_value(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-real-value")
    settings = Settings()
    assert settings.llm.api_key == "sk-real-value"
    path = settings.write_template(tmp_path / "crewforge.yaml")
    text = path.read_text()
    assert "sk-real-value" not in text
    assert yaml.safe_load(text)["llm"]["api_key"] == "${OPENAI_API_KEY}"


def test_yaml_env_reference_is_expanded_not_sent_literally(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk-1")
    cfg = tmp_path / "c.yaml"
    cfg.write_text("llm:\n  provider: groq\n  api_key: ${GROQ_API_KEY}\ncontent:\n  words: 300\n")
    settings = Settings.from_yaml(cfg)
    assert settings.llm.api_key == "gsk-1"
    assert settings.llm.headers["Authorization"] == "Bearer gsk-1"
    assert settings.content == {"words": 300}


def test_unset_yaml_reference_becomes_missing_key_error(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("llm:\n  api_key: ${NOT_SET_ANYWHERE}\n")
    settings = Settings.from_yaml(cfg)
    assert settings.llm.api_key == ""
    with pytest.raises(ConfigError, match="no API key"):
        settings.llm.require_valid()


def test_bad_yaml_is_a_config_error(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("- just\n- a list\n")
    with pytest.raises(ConfigError):
        Settings.from_yaml(cfg)


def test_expand_env_recurses(monkeypatch):
    monkeypatch.setenv("A", "1")
    assert expand_env({"x": ["${A}", {"y": "${A}-${B}"}], "n": 3}) == {
        "x": ["1", {"y": "1-"}],
        "n": 3,
    }


def test_retry_settings_are_validated():
    assert LLMConfig(api_key="k", max_retries=0).validate_config()
    assert LLMConfig(api_key="k", timeout=0).validate_config()


def test_academic_section_is_kept(tmp_path):
    # The academic recipe reads its own section; an unknown section would be dropped silently.
    cfg = tmp_path / "c.yaml"
    cfg.write_text("academic:\n  language: ms\n")
    assert Settings.from_yaml(cfg).academic == {"language": "ms"}
