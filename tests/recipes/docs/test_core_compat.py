"""documind's client / config / multi-backend / token-tracker tests, re-targeted.

documind had its own DocuMindConfig, LLMClient and TokenTracker; crewforge
has one shared core plus the ``docs:`` settings section. Each test keeps the
original guarantee and names the documind test it came from.
"""

from __future__ import annotations

import json
import time

import httpx
import pytest

from crewforge.core.client import ChatResponse, LLMClient, Message
from crewforge.core.config import LLMConfig, Settings
from crewforge.core.providers import DEFAULT_PROVIDER, PROVIDERS
from crewforge.core.usage import AgentUsage, UsageTracker
from crewforge.recipes.docs import DocsSettings
from tests.recipes.docs.fakes import completion


@pytest.fixture
def llm() -> LLMConfig:
    return LLMConfig(api_key="test-key-123", base_url="https://test.api.example.com/v1")


def _usage_body(content="Hello!", p=50, c=10):
    return {
        "model": "m",
        "choices": [{"message": {"content": content, "reasoning_content": "thinking..."}}],
        "usage": {"prompt_tokens": p, "completion_tokens": c, "total_tokens": p + c},
    }


def _client(llm, handler) -> LLMClient:
    return LLMClient(llm, transport=httpx.MockTransport(handler))


# --- tests/test_client.py --------------------------------------------------------


class TestClient:
    def test_init_with_config(self, llm):  # TestMiMoClient::test_init_with_config
        assert LLMClient(llm).config.api_key == "test-key-123"

    def test_base_url_strips_trailing_slash(self):  # ::test_base_url_strips_trailing_slash
        assert LLMConfig(api_key="k", base_url="https://example.com/v1/").base_url == (
            "https://example.com/v1"
        )

    def test_headers_use_bearer_by_default(self, llm):  # ::test_headers_use_bearer_by_default
        assert llm.headers["Authorization"] == "Bearer test-key-123"
        assert "api-key" not in llm.headers

    def test_headers_content_type(self, llm):  # ::test_headers_content_type
        assert llm.headers["Content-Type"] == "application/json"

    def test_initial_stats(self, llm):  # ::test_initial_stats
        client = LLMClient(llm)
        assert client.request_count == 0 and client.total_usage.total_tokens == 0

    async def test_chat_completion_success(self, llm):  # ::test_chat_completion_success
        client = _client(llm, lambda r: httpx.Response(200, json=_usage_body()))
        result = await client.chat([Message("user", "Hi")])
        assert isinstance(result, ChatResponse)
        assert result.content == "Hello!" and result.usage.total_tokens == 60
        assert result.reasoning == "thinking..."

    async def test_chat_completion_tracks_stats(self, llm):  # ::test_chat_completion_tracks_stats
        client = _client(llm, lambda r: httpx.Response(200, json=_usage_body(p=200, c=100)))
        await client.chat([{"role": "user", "content": "test"}])
        assert client.request_count == 1 and client.total_usage.total_tokens == 300

    async def test_close(self, llm):  # ::test_close
        client = _client(llm, lambda r: httpx.Response(200, json=_usage_body()))
        await client.chat([Message("user", "x")])
        await client.aclose()
        assert client._http.is_closed


class TestCompletionResponse:
    def test_default_values(self):
        r = ChatResponse(content="")
        assert r.content == "" and r.usage.total_tokens == 0

    def test_custom_values(self):
        r = completion("test", prompt_tokens=60, completion_tokens=40)
        assert r.content == "test" and r.usage.total_tokens == 100


class TestRealHttpTransport:
    async def test_non_streaming_request_and_parse(self, llm):
        seen: dict = {}

        def handler(request):
            seen["url"] = str(request.url)
            seen["auth"] = request.headers.get("authorization")
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json=_usage_body("Paris", 7, 1))

        async with _client(llm, handler) as client:
            result = await client.chat([Message("user", "?")])
        assert result.content == "Paris" and result.usage.total_tokens == 8
        assert seen["url"] == "https://test.api.example.com/v1/chat/completions"
        assert seen["auth"] == "Bearer test-key-123"
        assert seen["body"]["stream"] is False
        assert seen["body"]["model"] == llm.model

    async def test_null_content_becomes_empty_string(self, llm):
        def handler(request):
            return httpx.Response(200, json={"choices": [{"message": {"content": None}}]})

        async with _client(llm, handler) as client:
            result = await client.chat([Message("user", "?")])
        assert result.content == ""


# --- tests/test_config.py --------------------------------------------------------


class TestDocuMindConfig:
    def test_default_values(self):
        assert LLMConfig(api_key="test").provider == "openai"
        assert LLMConfig(api_key="test").model == "gpt-4o-mini"
        assert DocsSettings().chunk_size == 512

    def test_validate_no_key(self):
        assert any("OPENAI_API_KEY" in e for e in LLMConfig().validate_config())

    def test_validate_no_key_ok_for_ollama(self):
        assert LLMConfig(provider="ollama").validate_config() == []

    def test_validate_unknown_provider(self):
        problems = LLMConfig(provider="nope", api_key="k").validate_config()
        assert any("unknown provider" in e for e in problems)

    def test_validate_bad_chunk_overlap(self):
        problems = DocsSettings(chunk_size=100, chunk_overlap=200).problems()
        assert any("chunk_overlap" in e for e in problems)

    def test_validate_good_config(self):
        assert LLMConfig(api_key="k").validate_config() == []
        assert DocsSettings().problems() == []

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "env-key")
        assert Settings().llm.api_key == "env-key"

    def test_citation_format_validation(self):
        problems = DocsSettings(citation_format="invalid").problems()
        assert any("citation" in e.lower() for e in problems)


# --- tests/test_multi_backend.py -------------------------------------------------


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


class TestPresetResolution:
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
        # test_groq_preset / test_deepseek_preset / test_together_preset / test_mistral_preset
        c = LLMConfig(provider=provider, api_key="t")
        assert host in c.base_url and c.auth_style == "bearer"

    def test_unknown_provider_falls_back_to_default(self):
        # documind silently used OpenAI's URL; crewforge refuses to guess a URL.
        c = LLMConfig(provider="nope", api_key="x")
        assert c.base_url == "" and c.validate_config()

    def test_explicit_values_override_preset(self):
        c = LLMConfig(
            provider="openai", api_key="x", base_url="https://proxy.local/v1", model="custom"
        )
        assert (c.base_url, c.model) == ("https://proxy.local/v1", "custom")


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
        monkeypatch.setenv("CREWFORGE_PROVIDER", "openrouter")  # was DOCUMIND_PROVIDER
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-env")
        c = LLMConfig()
        assert c.provider == "openrouter" and c.api_key == "or-env"


class TestGenericOverrides:
    def test_documind_env_overrides_any_provider(self, monkeypatch):
        # DOCUMIND_API_KEY/BASE_URL/MODEL -> CREWFORGE_API_KEY/BASE_URL/MODEL
        monkeypatch.setenv("CREWFORGE_API_KEY", "generic-key")
        monkeypatch.setenv("CREWFORGE_BASE_URL", "http://localhost:8000/v1")
        monkeypatch.setenv("CREWFORGE_MODEL", "my-model")
        c = LLMConfig()
        assert c.provider == "openai"
        assert (c.api_key, c.base_url, c.model) == (
            "generic-key",
            "http://localhost:8000/v1",
            "my-model",
        )
        assert c.headers["Authorization"] == "Bearer generic-key"

    def test_preset_env_base_url(self, monkeypatch):
        monkeypatch.setenv("OPENAI_BASE_URL", "https://gateway.example/v1")
        assert LLMConfig(api_key="k").base_url == "https://gateway.example/v1"


class TestMiMoBackwardCompat:
    def test_mimo_defaults(self):
        c = LLMConfig(provider="mimo", api_key="test")
        assert c.provider == "mimo" and c.model == "mimo-v2.5-pro"
        assert "xiaomimimo.com" in c.base_url and c.headers["api-key"] == "test"

    def test_mimo_model_env(self, monkeypatch):
        monkeypatch.setenv("CREWFORGE_MODEL", "mimo-other")  # was MIMO_MODEL
        assert LLMConfig(provider="mimo", api_key="k").model == "mimo-other"

    def test_generic_aliases(self):
        # documind kept mimo_* fields as aliases; crewforge has only the generic names
        c = LLMConfig(provider="openai", api_key="sk-x")
        assert c.api_key == "sk-x" and not hasattr(c, "mimo_api_key")


# --- tests/test_token_tracker.py -------------------------------------------------


def _record(t: UsageTracker, agent: str, p: int, c: int, latency: float = 0.0) -> None:
    t.record(agent, completion(prompt_tokens=p, completion_tokens=c).usage, latency)


class TestTokenTracker:
    def test_initial_state(self):
        t = UsageTracker()
        assert t.total_tokens == 0 and t.total_calls == 0

    def test_record_single_call(self):
        t = UsageTracker()
        _record(t, "answerer", 100, 50, 200.0)
        usage = t.by_agent()["answerer"]
        assert isinstance(usage, AgentUsage)
        assert usage.agent == "answerer" and usage.total_tokens == 150

    def test_record_multiple_calls(self):
        t = UsageTracker()
        _record(t, "ingester", 200, 100)
        _record(t, "indexer", 300, 150)
        _record(t, "answerer", 400, 200)
        assert t.total_calls == 3 and t.total_tokens == 1350

    def test_by_agent_aggregation(self):
        t = UsageTracker()
        _record(t, "answerer", 100, 50)
        _record(t, "answerer", 200, 100)
        _record(t, "ingester", 150, 75)
        by_agent = t.by_agent()
        assert by_agent["answerer"].calls == 2 and by_agent["answerer"].total_tokens == 450
        assert by_agent["ingester"].calls == 1

    def test_summary_structure(self):
        # documind's summary also had a "projection" (extrapolated daily tokens);
        # crewforge reports only measured numbers, so that key must NOT exist.
        t = UsageTracker()
        _record(t, "test", 100, 50)
        summary = t.summary()
        assert {"calls", "total_tokens", "agents"} <= set(summary)
        assert "projection" not in summary

    def test_export_json(self, tmp_path):
        t = UsageTracker()
        _record(t, "test", 100, 50)
        out = t.save(tmp_path / "report.json")
        assert json.loads(out.read_text())["calls"] == 1

    def test_reset(self):
        t = UsageTracker()
        _record(t, "test", 100, 50)
        assert t.total_calls == 1
        t.reset()
        assert t.total_calls == 0 and t.total_tokens == 0

    def test_session_duration_positive(self):
        t = UsageTracker()
        time.sleep(0.01)
        assert t.duration_s > 0
