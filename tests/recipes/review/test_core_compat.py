"""codeguard's config / client / token-tracker tests, re-targeted at crewforge.core.

codeguard had its own LLMConfig, MiMoConfig, LLMClient and TokenTracker. In
crewforge those are one shared core; each test below keeps the original
guarantee and names the codeguard test it came from.
"""

from __future__ import annotations

import json
import time

import httpx
import pytest

from crewforge.core.client import LLMClient, Message, Usage
from crewforge.core.config import LLMConfig, Settings
from crewforge.core.errors import LLMHTTPError
from crewforge.core.providers import DEFAULT_PROVIDER, PROVIDERS
from crewforge.core.usage import AgentUsage, UsageTracker


def mimo(**kw) -> LLMConfig:
    return LLMConfig(provider="mimo", **kw)


# --- tests/unit/test_config.py -------------------------------------------------


class TestMiMoConfig:
    def test_default_model(self):  # TestMiMoConfig::test_default_model
        assert mimo(api_key="test").model == "mimo-v2.5-pro"

    def test_api_key_header_not_bearer(self):  # ::test_api_key_header_not_bearer
        headers = mimo(api_key="my-key").headers
        assert "api-key" in headers and "Authorization" not in headers

    def test_default_temperature_low(self):  # ::test_default_temperature_low
        assert mimo(api_key="test").temperature == 0.3

    def test_base_url(self):  # ::test_base_url
        assert "token-plan-sgp.xiaomimimo.com" in mimo(api_key="test").base_url


class TestReviewConfig:
    def test_defaults(self):  # TestReviewConfig::test_defaults -> review: YAML section
        from crewforge.recipes.review.cli import ReviewSettings
        from crewforge.recipes.review.sources import DEFAULT_MAX_FILE_BYTES

        s = ReviewSettings()
        assert "security" in s.agents and len(s.agents) == 6
        assert s.max_file_bytes == DEFAULT_MAX_FILE_BYTES


class TestCodeGuardConfig:
    def test_from_env(self, monkeypatch):  # TestCodeGuardConfig::test_from_env
        monkeypatch.setenv("OPENAI_API_KEY", "env-key")
        assert Settings().llm.api_key == "env-key"

    def test_output_format_default(self):  # ::test_output_format_default -> CLI default
        from crewforge.recipes.review.cli import review

        fmt = next(p for p in review.params if p.name == "fmt")
        assert fmt.default == "text"


# --- tests/unit/test_llm_client.py ---------------------------------------------


def _client(handler, **cfg) -> LLMClient:
    async def no_sleep(_):
        return None

    config = LLMConfig(provider="openai", api_key="k", retry_delay=0, **cfg)
    return LLMClient(config, transport=httpx.MockTransport(handler), sleep=no_sleep)


def _ok(content="hi", usage=None):
    body = {"model": "m", "choices": [{"message": {"content": content}}]}
    if usage is not None:
        body["usage"] = usage
    return httpx.Response(200, json=body)


async def test_payload_disables_streaming_and_honours_zero_temperature():
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return _ok()

    resp = await _client(handler).chat([Message("user", "x")], temperature=0.0)
    assert resp.content == "hi"
    assert seen["stream"] is False and seen["temperature"] == 0.0


async def test_null_usage_and_content_are_tolerated():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": None}}],
                "usage": {"total_tokens": 7, "prompt_tokens_details": None},
            },
        )

    resp = await _client(handler).chat([Message("user", "x")])
    assert resp.content == ""
    assert resp.usage.total_tokens == 7 and resp.usage.cached_tokens == 0


async def test_retries_server_errors_then_succeeds():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503) if len(calls) < 2 else _ok("done")

    resp = await _client(handler, max_retries=3).chat([Message("user", "x")])
    assert resp.content == "done" and len(calls) == 2


async def test_does_not_retry_auth_errors():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(401, json={"error": "bad key"})

    with pytest.raises(LLMHTTPError):
        await _client(handler, max_retries=3).chat([Message("user", "x")])
    assert len(calls) == 1


# --- tests/unit/test_llm_config.py ---------------------------------------------


class TestProviderPresets:
    def test_known_providers_present(self):
        for p in (
            "mimo",
            "openai",
            "openrouter",
            "ollama",
            "groq",
            "deepseek",
            "together",
            "mistral",
        ):
            assert p in PROVIDERS

    def test_default_provider_is_openai(self):
        assert DEFAULT_PROVIDER == "openai"

    def test_default_config_uses_openai(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-default")
        llm = Settings().llm
        assert llm.provider == "openai"
        assert llm.base_url == "https://api.openai.com/v1"
        assert llm.headers["Authorization"] == "Bearer sk-default"


class TestLLMConfigPresetResolution:
    def test_openai_preset(self):
        c = LLMConfig(provider="openai", api_key="sk-test")
        assert (c.base_url, c.model, c.auth_style) == (
            "https://api.openai.com/v1",
            "gpt-4o-mini",
            "bearer",
        )

    def test_openrouter_preset(self):
        c = LLMConfig(provider="openrouter", api_key="or-test")
        assert "openrouter.ai" in c.base_url and c.auth_style == "bearer"

    def test_ollama_preset(self):
        c = LLMConfig(provider="ollama")
        assert "localhost:11434" in c.base_url and c.model == "llama3.1"

    def test_unknown_provider_falls_back_to_default(self):
        # crewforge reports the unknown name instead of silently using OpenAI's URL,
        # but auth stays OpenAI-style Bearer so custom endpoints keep working.
        c = LLMConfig(provider="does-not-exist", api_key="x")
        assert c.auth_style == "bearer"
        assert any("unknown provider" in p for p in c.validate_config())

    def test_custom_endpoint_via_unknown_provider(self):
        c = LLMConfig(
            provider="custom", base_url="http://localhost:8080/v1", model="m", api_key="k"
        )
        assert c.base_url == "http://localhost:8080/v1"
        assert c.headers["Authorization"] == "Bearer k"

    @pytest.mark.parametrize(
        "provider,host",
        [
            ("groq", "api.groq.com"),  # test_groq_preset
            ("deepseek", "api.deepseek.com"),  # test_deepseek_preset
            ("together", "api.together.xyz"),  # test_together_preset
            ("mistral", "api.mistral.ai"),  # test_mistral_preset
        ],
    )
    def test_bearer_presets(self, provider, host):
        c = LLMConfig(provider=provider, api_key="t")
        assert host in c.base_url and c.auth_style == "bearer"

    def test_explicit_values_override_preset(self):
        c = LLMConfig(provider="openai", base_url="https://proxy.local/v1", model="custom")
        assert (c.base_url, c.model) == ("https://proxy.local/v1", "custom")

    def test_default_temperature_low_for_code_review(self):
        assert LLMConfig(provider="openai", api_key="x").temperature == 0.3


class TestAuthStyles:
    def test_bearer_auth_header(self):
        h = LLMConfig(provider="openai", api_key="sk-abc").headers
        assert h["Authorization"] == "Bearer sk-abc" and "api-key" not in h

    def test_api_key_auth_header(self):
        h = LLMConfig(provider="mimo", api_key="mimo-secret").headers
        assert h["api-key"] == "mimo-secret" and "Authorization" not in h

    def test_explicit_auth_style_override(self):
        c = LLMConfig(provider="mimo", api_key="k", auth_style="bearer")
        assert c.headers["Authorization"] == "Bearer k"


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
    """codeguard kept MiMoConfig/MiMoClient aliases; crewforge has the mimo preset."""

    def test_mimo_config_defaults(self):
        c = mimo(api_key="test")
        assert c.provider == "mimo" and c.model == "mimo-v2.5-pro"
        assert "xiaomimimo.com" in c.base_url
        assert c.headers["api-key"] == "test" and c.temperature == 0.3

    def test_root_config_mimo_property_aliases_llm(self):
        s = Settings(llm={"provider": "mimo", "api_key": "k"})
        assert s.llm.provider == "mimo"

    def test_legacy_mimo_yaml_block_maps_to_llm(self, tmp_path):
        cfg = tmp_path / "c.yaml"
        cfg.write_text("llm:\n  provider: mimo\n  api_key: legacy\n  model: mimo-v2.5-pro\n")
        assert Settings.from_yaml(cfg).llm.api_key == "legacy"

    def test_new_llm_yaml_block(self):
        s = Settings(**{"llm": {"provider": "openai", "api_key": "sk-x"}})
        assert s.llm.provider == "openai" and s.llm.auth_style == "bearer"

    async def test_mimo_client_shim_reexports_llm_client(self):
        seen = {}

        def handler(request):
            seen.update(request.headers)
            return _ok()

        client = LLMClient(mimo(api_key="mk"), transport=httpx.MockTransport(handler))
        await client.chat([Message("user", "x")])
        assert seen["api-key"] == "mk" and "authorization" not in seen


# --- tests/unit/test_token_tracker.py ------------------------------------------


def _u(tokens: int) -> Usage:
    return Usage(tokens, 0, tokens, reported=True)


class TestTokenTracker:
    def test_initial_state(self):
        assert UsageTracker().total_tokens == 0

    def test_record(self):
        t = UsageTracker()
        t.record("security", _u(500), 100)
        assert t.total_tokens == 500

    def test_multiple_agents(self):
        t = UsageTracker()
        t.record("security", _u(500), 100)
        t.record("style", _u(300), 80)
        assert t.total_tokens == 800

    def test_duration(self):
        t = UsageTracker()
        time.sleep(0.01)
        t.finish()
        assert t.duration_s > 0

    def test_report(self):
        t = UsageTracker()
        t.record("security", _u(500), 100)
        assert "security" in t.summary()["agents"]
        assert "500 tokens" in t.one_line()


class TestAgentMetrics:
    def test_defaults(self):
        m = AgentUsage("test")
        assert (m.calls, m.avg_latency_ms, m.total_tokens) == (0, 0, 0)

    def test_calculations(self):
        m = AgentUsage("test", calls=2, total_tokens=1000, latency_ms=200)
        assert m.avg_latency_ms == 100
        assert m.total_tokens / m.calls == 500
