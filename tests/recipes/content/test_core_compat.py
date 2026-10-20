"""contentforge's config / llm-config / token-tracker tests, re-targeted.

contentforge had its own LLMConfig, MiMoConfig, ContentForgeConfig and
TokenTracker. crewforge has one core (``LLMConfig``, ``Settings``,
``UsageTracker``) plus the ``content:`` settings section. Each test keeps the
original guarantee; comments name the contentforge test where it differs.
"""

from __future__ import annotations

import json
import time

import pytest
import yaml

from crewforge.core.client import Usage
from crewforge.core.config import LLMConfig, Settings
from crewforge.core.providers import DEFAULT_PROVIDER, PROVIDERS
from crewforge.core.usage import AgentUsage, UsageTracker
from crewforge.recipes.content import AgentConfig, ContentSettings, PipelineConfig


def mimo(**kw) -> LLMConfig:
    return LLMConfig(provider="mimo", **kw)


# --- tests/unit/test_config.py -------------------------------------------------


class TestMiMoConfig:
    def test_default_values(self):
        c = mimo(api_key="test")
        assert c.model == "mimo-v2.5-pro"
        assert (c.max_tokens, c.timeout, c.max_retries) == (4096, 120, 3)
        # contentforge's sampling default (0.7) now lives on the content agents.
        from crewforge.recipes.content.agents import ContentAgent

        assert ContentAgent.temperature == 0.7

    def test_custom_values(self):
        c = mimo(api_key="custom-key", model="mimo-v2.5-lite", max_tokens=2048, temperature=0.5)
        assert (c.api_key, c.model, c.max_tokens, c.temperature) == (
            "custom-key",
            "mimo-v2.5-lite",
            2048,
            0.5,
        )

    def test_headers_use_api_key_not_bearer(self):
        h = mimo(api_key="my-secret-key").headers
        assert h["api-key"] == "my-secret-key" and "Authorization" not in h

    def test_headers_content_type(self):
        assert mimo(api_key="test").headers["Content-Type"] == "application/json"

    def test_base_url_default(self):
        assert "token-plan-sgp.xiaomimimo.com" in mimo(api_key="test").base_url

    def test_base_url_custom(self):
        assert mimo(api_key="t", base_url="https://custom.api.com/v1").base_url == (
            "https://custom.api.com/v1"
        )

    def test_from_env_uses_env_vars(self, monkeypatch):
        monkeypatch.setenv("MIMO_API_KEY", "env-key-123")
        monkeypatch.setenv("MIMO_BASE_URL", "https://env.api.com/v1")
        c = mimo()
        assert (c.api_key, c.base_url) == ("env-key-123", "https://env.api.com/v1")


class TestPipelineConfig:
    def test_defaults(self):
        c = PipelineConfig()
        assert (c.target_word_count, c.language, c.seo_enabled) == (2000, "en", True)
        assert (c.quality_threshold, c.max_iterations) == (0.8, 3)

    def test_translation_defaults(self):
        c = PipelineConfig()
        assert c.enable_translation is False
        assert {"zh", "ms"} <= set(c.target_languages)

    def test_publish_targets(self):
        c = PipelineConfig(publish_targets=["html", "json"])  # wordpress was never implemented
        assert c.publish_targets == ["html", "json"]


class TestAgentConfig:
    def test_defaults(self):
        c = AgentConfig(name="test-agent")
        assert (c.name, c.enabled, c.model_override) == ("test-agent", True, None)

    def test_overrides(self):
        c = AgentConfig(name="writer", temperature_override=0.9, max_tokens_override=8192)
        assert (c.temperature_override, c.max_tokens_override) == (0.9, 8192)


class TestContentForgeConfig:
    def test_default_config(self):
        s = Settings()
        assert (s.llm.provider, s.llm.model) == ("openai", "gpt-4o-mini")
        assert ContentSettings().output_dir == "./output"

    def test_from_yaml(self, tmp_path):
        path = tmp_path / "c.yaml"
        path.write_text(
            yaml.safe_dump(
                {
                    "llm": {"provider": "mimo", "api_key": "yaml-key"},
                    "content": {"pipeline": {"target_word_count": 3000}},
                }
            )
        )
        s = Settings.from_yaml(path)
        assert s.llm.api_key == "yaml-key"
        assert ContentSettings.from_mapping(s.content).pipeline.target_word_count == 3000

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "env-test-key")
        assert Settings().llm.api_key == "env-test-key"

    def test_from_env_mimo_provider(self, monkeypatch):
        monkeypatch.setenv("CREWFORGE_PROVIDER", "mimo")  # was CONTENTFORGE_PROVIDER
        monkeypatch.setenv("MIMO_API_KEY", "mimo-key")
        llm = Settings().llm
        assert llm.provider == "mimo" and llm.headers["api-key"] == "mimo-key"

    def test_get_agent_config_existing(self):
        s = ContentSettings(agents=[AgentConfig(name="writer", temperature_override=0.9)])
        assert s.get_agent_config("writer").temperature_override == 0.9

    def test_get_agent_config_missing_returns_default(self):
        c = ContentSettings().get_agent_config("nonexistent")
        assert (c.name, c.enabled) == ("nonexistent", True)


# --- tests/unit/test_llm_config.py ---------------------------------------------


class TestProviderPresets:
    def test_known_providers_present(self):
        for p in ("mimo", "openai", "openrouter", "ollama", "groq", "deepseek", "together"):
            assert p in PROVIDERS
        assert "mistral" in PROVIDERS

    def test_default_provider_is_openai(self):
        assert DEFAULT_PROVIDER == "openai"

    def test_default_llm_config_uses_openai(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-default")
        c = LLMConfig()
        assert c.provider == "openai" and c.base_url == "https://api.openai.com/v1"
        assert c.headers["Authorization"] == "Bearer sk-default"


class TestLLMConfigPresetResolution:
    def test_openai_preset(self):
        c = LLMConfig(provider="openai", api_key="sk-test")
        assert (c.base_url, c.model, c.auth_style) == (
            "https://api.openai.com/v1",
            "gpt-4o-mini",
            "bearer",
        )

    def test_openrouter_preset(self):
        c = LLMConfig(provider="openrouter", api_key="or")
        assert "openrouter.ai" in c.base_url and c.auth_style == "bearer"

    def test_ollama_preset(self):
        c = LLMConfig(provider="ollama")
        assert "localhost:11434" in c.base_url and c.model == "llama3.1"

    def test_unknown_provider_falls_back_to_default(self):
        # contentforge's fix: unknown names use Bearer (not MiMo's api-key header).
        # crewforge also refuses to guess a URL and reports the unknown name.
        c = LLMConfig(provider="does-not-exist", api_key="x")
        assert c.auth_style == "bearer"
        assert any("unknown provider" in p for p in c.validate_config())

    def test_custom_provider_with_base_url_uses_bearer(self):
        c = LLMConfig(provider="custom", base_url="http://localhost:8000/v1", api_key="k")
        assert c.base_url == "http://localhost:8000/v1"
        assert c.headers["Authorization"] == "Bearer k"

    @pytest.mark.parametrize(
        "provider,host",
        [
            ("groq", "api.groq.com"),
            ("deepseek", "api.deepseek.com"),
            ("together", "api.together.xyz"),
            ("mistral", "api.mistral.ai"),
        ],
    )
    def test_bearer_presets(self, provider, host):
        c = LLMConfig(provider=provider, api_key="t")
        assert host in c.base_url and c.auth_style == "bearer"

    def test_explicit_values_override_preset(self):
        c = LLMConfig(provider="openai", base_url="https://proxy.local/v1", model="custom")
        assert (c.base_url, c.model) == ("https://proxy.local/v1", "custom")


class TestAuthStyles:
    def test_bearer_auth_header(self):
        h = LLMConfig(provider="openai", api_key="sk-abc").headers
        assert h["Authorization"] == "Bearer sk-abc" and "api-key" not in h

    def test_api_key_auth_header(self):
        h = mimo(api_key="mimo-secret").headers
        assert h["api-key"] == "mimo-secret" and "Authorization" not in h

    def test_explicit_auth_style_override(self):
        assert mimo(api_key="k", auth_style="bearer").headers["Authorization"] == "Bearer k"


class TestEnvResolution:
    def test_openai_env_key(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
        assert LLMConfig(provider="openai").api_key == "sk-from-env"

    def test_openrouter_env_base(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-env")
        monkeypatch.setenv("OPENROUTER_BASE_URL", "https://env.openrouter/v1")
        c = LLMConfig(provider="openrouter")
        assert (c.api_key, c.base_url) == ("or-env", "https://env.openrouter/v1")


class TestMiMoBackwardCompat:
    def test_mimo_config_defaults_to_mimo_provider(self):
        c = mimo(api_key="t")
        assert c.provider == "mimo" and c.headers["api-key"] == "t"

    def test_root_config_mimo_property_aliases_llm(self):
        assert Settings(llm={"provider": "mimo", "api_key": "k"}).llm.provider == "mimo"

    def test_legacy_mimo_yaml_block_maps_to_llm(self, tmp_path):
        path = tmp_path / "c.yaml"
        path.write_text("llm:\n  provider: mimo\n  api_key: legacy\n")
        assert Settings.from_yaml(path).llm.api_key == "legacy"

    def test_new_llm_yaml_block(self):
        s = Settings(llm={"provider": "openai", "api_key": "sk-x"})
        assert s.llm.provider == "openai" and s.llm.auth_style == "bearer"


class TestEnvConfiguration:
    def test_from_env_selects_provider_and_model(self, monkeypatch):
        monkeypatch.setenv("CREWFORGE_PROVIDER", "openrouter")
        monkeypatch.setenv("CREWFORGE_MODEL", "some/model")
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
        llm = Settings().llm
        assert (llm.provider, llm.model, llm.api_key) == ("openrouter", "some/model", "or-key")
        assert "openrouter.ai" in llm.base_url

    def test_from_env_defaults_to_openai(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
        llm = Settings().llm
        assert (llm.provider, llm.api_key) == ("openai", "sk-env")

    def test_yaml_env_reference_is_expanded(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
        path = tmp_path / "cf.yaml"
        path.write_text("llm:\n  provider: openai\n  api_key: ${OPENAI_API_KEY}\n")
        assert Settings.from_yaml(path).llm.api_key == "sk-from-env"

    def test_yaml_unset_env_reference_falls_back_to_preset_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-preset")
        path = tmp_path / "cf.yaml"
        path.write_text("llm:\n  api_key: ${MISSING_VAR}\n")
        assert Settings.from_yaml(path).llm.api_key == "sk-preset"

    def test_template_never_contains_resolved_key(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
        data = Settings().to_template()
        assert data["llm"]["api_key"] == "${OPENAI_API_KEY}"
        assert "sk-secret" not in str(data)


# --- tests/unit/test_token_tracker.py ------------------------------------------


def _u(p: int, c: int, cached: int = 0) -> Usage:
    return Usage(p, c, p + c, cached, reported=True)


@pytest.fixture
def tracker() -> UsageTracker:
    return UsageTracker()


class TestAgentMetrics:
    def test_initial_state(self):
        m = AgentUsage("test")
        assert (m.calls, m.total_tokens, m.avg_latency_ms) == (0, 0, 0.0)
        assert (m.tokens_per_call, m.cache_hit_rate) == (0.0, 0.0)

    def test_record_single_call(self):
        m = AgentUsage(
            "test",
            calls=1,
            prompt_tokens=500,
            completion_tokens=300,
            total_tokens=800,
            latency_ms=150.0,
        )
        assert (m.avg_latency_ms, m.tokens_per_call) == (150.0, 800.0)

    def test_record_multiple_calls(self):
        m = AgentUsage(
            "test",
            calls=3,
            prompt_tokens=1500,
            completion_tokens=900,
            total_tokens=2400,
            latency_ms=450.0,
        )
        assert (m.avg_latency_ms, m.tokens_per_call) == (150.0, 800.0)

    def test_cache_hit_rate(self):
        assert AgentUsage("test", prompt_tokens=1000, cached_tokens=250).cache_hit_rate == 0.25

    def test_cache_hit_rate_zero_prompt(self):
        assert AgentUsage("test").cache_hit_rate == 0.0

    def test_to_dict(self):
        d = AgentUsage("research", calls=2, total_tokens=1600).to_dict()
        assert (d["agent"], d["calls"], d["total_tokens"]) == ("research", 2, 1600)


class TestTokenTracker:
    def test_initial_state(self, tracker):
        assert tracker.total_tokens == 0 and tracker.total_calls == 0

    def test_record_single(self, tracker):
        tracker.record("research", _u(500, 300), 100)
        assert (tracker.total_tokens, tracker.total_calls) == (800, 1)

    def test_record_multiple_agents(self, tracker):
        tracker.record("research", _u(500, 300), 100)
        tracker.record("writer", _u(1000, 800), 200)
        assert (tracker.total_tokens, tracker.total_calls) == (2600, 2)

    def test_record_accumulates(self, tracker):
        tracker.record("research", _u(500, 300), 100)
        tracker.record("research", _u(600, 400), 120)
        assert (tracker.total_tokens, tracker.total_calls) == (1800, 2)

    def test_pipeline_duration(self, tracker):
        time.sleep(0.01)
        tracker.finish()
        assert tracker.duration_s > 0

    def test_summary_structure(self, tracker):
        tracker.record("research", _u(500, 300), 100)
        summary = tracker.summary()
        assert {"run_id", "total_tokens", "agents"} <= set(summary)
        assert "research" in summary["agents"]

    def test_report_contains_headers(self, tracker):
        tracker.record("research", _u(500, 300), 100)
        report = tracker.report()
        assert "Token usage" in report and "research" in report

    def test_save_creates_file(self, tracker, tmp_path):
        tracker.record("research", _u(500, 300), 100)
        path = tracker.save(tmp_path / "metrics" / f"{tracker.run_id}.json")
        assert json.loads(path.read_text())["total_tokens"] == 800

    def test_save_with_custom_path(self, tracker, tmp_path):
        tracker.record("test", _u(100, 50), 50)
        path = tracker.save(tmp_path / "custom.json")
        assert json.loads(path.read_text())["total_tokens"] == 150

    def test_cached_tokens_tracking(self, tracker):
        tracker.record("research", _u(500, 300, cached=200), 100)
        assert tracker.summary()["agents"]["research"]["cached_tokens"] == 200

    def test_error_tracking(self, tracker):
        tracker.record("research", None, 50, error=True, retries=2)
        agent = tracker.summary()["agents"]["research"]
        assert (agent["errors"], agent["retries"]) == (1, 2)
