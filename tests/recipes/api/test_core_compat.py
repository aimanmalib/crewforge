"""apiforge's client / config / multi-backend / tracker / exception tests, re-targeted.

apiforge had its own APIForgeConfig, LLMClient, TokenTracker and exception
classes; crewforge has one core. Each test keeps the original guarantee and
names the apiforge test it came from where the mapping is not obvious.
"""

from __future__ import annotations

import json

import httpx
import pytest

from crewforge.core.client import ChatResponse, LLMClient, Message
from crewforge.core.config import LLMConfig, Settings
from crewforge.core.errors import (
    AgentError,
    CrewForgeError,
    LLMError,
    LLMHTTPError,
    OutputParseError,
)
from crewforge.core.providers import DEFAULT_PROVIDER, PROVIDERS
from crewforge.core.usage import UsageTracker
from crewforge.recipes.api.agents import ValidateAgent
from tests.recipes.api.fakes import completion


def _record(t: UsageTracker, agent: str, p: int, c: int) -> None:
    t.record(agent, completion(prompt_tokens=p, completion_tokens=c).usage)


# --- tests/test_client.py --------------------------------------------------------


class TestLLMClient:
    async def test_mimo_alias(self):
        # MiMoClient was an alias; the one core client speaks MiMo's api-key header.
        seen = {}

        def handler(request):
            seen.update(request.headers)
            return httpx.Response(200, json={"choices": [{"message": {"content": "x"}}]})

        cfg = LLMConfig(provider="mimo", api_key="mk")
        await LLMClient(cfg, transport=httpx.MockTransport(handler)).chat([Message("user", "x")])
        assert seen["api-key"] == "mk"

    def test_init(self, config):
        assert LLMClient(config).config.api_key == "test-key"

    def test_headers_default_to_bearer(self, config):
        assert config.headers["Authorization"] == "Bearer test-key"
        assert "api-key" not in config.headers

    def test_headers_use_api_key_for_mimo(self):
        h = LLMConfig(provider="mimo", api_key="test-key").headers
        assert h["api-key"] == "test-key" and "Authorization" not in h

    def test_base_url_strips_slash(self):
        assert LLMConfig(api_key="k", base_url="https://x.com/v1/").base_url == "https://x.com/v1"

    def test_initial_stats(self, config):
        assert LLMClient(config).request_count == 0

    def test_completion_response_defaults(self):
        r = ChatResponse(content="")
        assert r.content == "" and r.usage.total_tokens == 0


# --- tests/test_config.py + test_more.py::TestConfigEdgeCases -------------------


class TestConfig:
    def test_default(self):
        c = LLMConfig(api_key="k")
        assert (c.provider, c.model) == ("openai", "gpt-4o-mini")

    def test_validate_no_key(self):
        problems = LLMConfig().validate_config()
        assert any("OPENAI_API_KEY" in e for e in problems)
        assert any("CREWFORGE_API_KEY" in e for e in problems)  # was APIFORGE_API_KEY

    def test_validate_no_key_names_provider_env(self):
        assert any(
            "OPENROUTER_API_KEY" in e for e in LLMConfig(provider="openrouter").validate_config()
        )

    def test_validate_bad_framework(self):
        # apiforge accepted framework=flask|express but only ever generated FastAPI;
        # crewforge has no framework switch, so the CLI exposes none.
        from crewforge.recipes.api.cli import scaffold

        assert "framework" not in {p.name for p in scaffold.params}

    def test_validate_good(self):
        assert LLMConfig(api_key="k").validate_config() == []

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "env-k")
        assert Settings().llm.api_key == "env-k"

    def test_custom_model(self):  # test_more.py
        assert LLMConfig(api_key="k", model="custom-model").model == "custom-model"

    def test_custom_base_url(self):  # test_more.py
        c = LLMConfig(api_key="k", base_url="https://custom.api.com/v1")
        assert c.base_url == "https://custom.api.com/v1"


# --- tests/test_multi_backend.py -------------------------------------------------


class TestProviderPresets:
    def test_known_providers_present(self):
        for p in ("mimo", "openai", "openrouter", "ollama", "groq", "deepseek", "together"):
            assert p in PROVIDERS
        assert "mistral" in PROVIDERS

    def test_default_provider_is_openai(self):
        assert DEFAULT_PROVIDER == "openai"


class TestPresetResolution:
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
        c = LLMConfig(provider="ollama", api_key="x")
        assert "localhost:11434" in c.base_url and c.model == "llama3.1"

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

    def test_unknown_provider_falls_back_to_default(self):
        c = LLMConfig(provider="nope", api_key="x")
        assert c.base_url == "" and any("unknown provider" in p for p in c.validate_config())

    def test_explicit_values_override_preset(self):
        c = LLMConfig(provider="openai", api_key="x", base_url="https://p/v1", model="custom")
        assert (c.base_url, c.model) == ("https://p/v1", "custom")


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

    def test_provider_from_env(self, monkeypatch):
        monkeypatch.setenv("CREWFORGE_PROVIDER", "openrouter")
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-env")
        c = LLMConfig()
        assert (c.provider, c.api_key) == ("openrouter", "or-env")

    def test_generic_env_overrides_any_provider(self, monkeypatch):
        monkeypatch.setenv("CREWFORGE_API_KEY", "generic")
        monkeypatch.setenv("CREWFORGE_BASE_URL", "http://localhost:8000/v1")
        monkeypatch.setenv("CREWFORGE_MODEL", "m")
        c = LLMConfig()
        assert (c.api_key, c.base_url, c.model) == ("generic", "http://localhost:8000/v1", "m")

    def test_mimo_key_not_sent_to_other_providers(self, monkeypatch):
        monkeypatch.setenv("MIMO_API_KEY", "mimo-only")
        c = LLMConfig(provider="openai")
        assert c.api_key == "" and "mimo-only" not in str(c.headers)


class TestMiMo:
    def test_mimo_preset(self, monkeypatch):
        monkeypatch.setenv("MIMO_API_KEY", "mk")
        c = LLMConfig(provider="mimo")
        assert c.api_key == "mk" and c.headers["api-key"] == "mk"

    def test_mimo_default_model(self):
        assert LLMConfig(provider="mimo", api_key="k").model == "mimo-v2.5-pro"

    def test_generic_aliases(self):
        c = LLMConfig(api_key="sk-x")
        assert c.api_key == "sk-x" and not hasattr(c, "mimo_api_key")


# --- tests/test_token_tracker.py + test_more.py::TestTokenTrackerEdgeCases -------


class TestTokenTracker:
    def test_initial(self):
        t = UsageTracker()
        assert t.total_tokens == 0 and t.total_calls == 0

    def test_record(self):
        t = UsageTracker()
        _record(t, "parser", 100, 50)
        assert (t.total_calls, t.total_tokens) == (1, 150)

    def test_by_agent(self):
        t = UsageTracker()
        _record(t, "parser", 100, 50)
        _record(t, "parser", 200, 100)
        _record(t, "schema", 150, 75)
        by = t.by_agent()
        assert (by["parser"].calls, by["schema"].calls) == (2, 1)

    def test_summary(self):
        # apiforge's summary carried hand-typed "daily_estimates_millions";
        # crewforge reports only provider-reported numbers.
        t = UsageTracker()
        _record(t, "test", 100, 50)
        s = t.summary()
        assert s["calls"] == 1
        assert not any("estimate" in k for k in s)

    def test_reset(self):
        t = UsageTracker()
        _record(t, "test", 100, 50)
        t.reset()
        assert t.total_calls == 0

    def test_multiple_agents_summary(self):  # test_more.py
        t = UsageTracker()
        _record(t, "parser", 100, 50)
        _record(t, "schema", 200, 100)
        _record(t, "validator", 50, 25)
        s = t.summary()
        assert (s["calls"], s["total_tokens"]) == (3, 525)

    def test_export_json(self, tmp_path):  # test_more.py
        t = UsageTracker()
        _record(t, "test", 100, 50)
        p = t.save(tmp_path / "stats.json")
        assert json.loads(p.read_text())["calls"] == 1


# --- tests/test_exceptions.py + test_more.py::TestExceptionHierarchy ------------


class TestExceptions:
    def test_base_error(self):
        e = CrewForgeError("test error")  # was APIForgeError
        assert str(e) == "test error"

    def test_base_error_with_details(self):
        e = OutputParseError("parser", "no JSON found", excerpt="Sure!")
        assert e.agent == "parser" and e.excerpt == "Sure!"

    def test_parse_error(self):
        assert isinstance(OutputParseError("parser", "x"), CrewForgeError)

    def test_generation_error(self):
        assert isinstance(AgentError("router", "failed"), CrewForgeError)

    async def test_validation_error(self):
        # apiforge's ValidationError was never raised; validation is a result object
        result = await ValidateAgent().validate({})
        assert result.valid is False and result.errors

    def test_mimo_api_error(self):
        e = LLMHTTPError(500, "api err")
        assert e.status_code == 500 and isinstance(e, LLMError)

    def test_quota_exceeded(self):
        assert isinstance(LLMHTTPError(429, "quota"), LLMError)

    async def test_rate_limit(self):
        # RateLimitError(retry_after=30) -> the client honours Retry-After itself
        sleeps = []

        async def sleep(s):
            sleeps.append(s)

        calls = []

        def handler(request):
            calls.append(1)
            if len(calls) == 1:
                return httpx.Response(429, headers={"Retry-After": "30"})
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

        cfg = LLMConfig(api_key="k", max_retry_delay=60)
        client = LLMClient(cfg, transport=httpx.MockTransport(handler), sleep=sleep)
        await client.chat([Message("user", "x")])
        assert sleeps == [30.0]

    def test_inheritance_chain(self):
        assert issubclass(LLMHTTPError, LLMError)
        assert issubclass(LLMError, CrewForgeError)
        assert issubclass(CrewForgeError, Exception)

    def test_mimo_error_chain(self):  # test_more.py
        e = LLMHTTPError(429, "too fast", attempts=3)
        assert isinstance(e, LLMError) and isinstance(e, CrewForgeError) and e.attempts == 3
