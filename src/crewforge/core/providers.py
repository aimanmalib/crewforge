"""Provider presets for OpenAI-compatible ``/chat/completions`` endpoints.

A preset only supplies *defaults*: base URL, auth header style, a default
model and the environment variables that hold the key and an optional base-URL
override. Anything can be overridden explicitly or through the generic
``CREWFORGE_*`` variables, so any compatible server works via ``custom``.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Generic environment variables that apply to whichever provider is active.
ENV_PROVIDER = "CREWFORGE_PROVIDER"
ENV_API_KEY = "CREWFORGE_API_KEY"
ENV_BASE_URL = "CREWFORGE_BASE_URL"
ENV_MODEL = "CREWFORGE_MODEL"

DEFAULT_PROVIDER = "openai"


@dataclass(frozen=True)
class Provider:
    name: str
    label: str
    base_url: str
    default_model: str
    env_key: str
    env_base: str
    auth_style: str = "bearer"  # "bearer" -> Authorization: Bearer; "api-key" -> api-key header
    keyless: bool = False  # local servers that accept requests without a key


PROVIDERS: dict[str, Provider] = {
    p.name: p
    for p in (
        Provider(
            "openai",
            "OpenAI",
            "https://api.openai.com/v1",
            "gpt-4o-mini",
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
        ),
        Provider(
            "openrouter",
            "OpenRouter",
            "https://openrouter.ai/api/v1",
            "openai/gpt-4o-mini",
            "OPENROUTER_API_KEY",
            "OPENROUTER_BASE_URL",
        ),
        Provider(
            "groq",
            "Groq",
            "https://api.groq.com/openai/v1",
            "llama-3.3-70b-versatile",
            "GROQ_API_KEY",
            "GROQ_BASE_URL",
        ),
        Provider(
            "deepseek",
            "DeepSeek",
            "https://api.deepseek.com/v1",
            "deepseek-chat",
            "DEEPSEEK_API_KEY",
            "DEEPSEEK_BASE_URL",
        ),
        Provider(
            "together",
            "Together AI",
            "https://api.together.xyz/v1",
            "meta-llama/Llama-3.3-70B-Instruct-Turbo",
            "TOGETHER_API_KEY",
            "TOGETHER_BASE_URL",
        ),
        Provider(
            "mistral",
            "Mistral",
            "https://api.mistral.ai/v1",
            "mistral-small-latest",
            "MISTRAL_API_KEY",
            "MISTRAL_BASE_URL",
        ),
        Provider(
            "ollama",
            "Ollama (local)",
            "http://localhost:11434/v1",
            "llama3.1",
            "OLLAMA_API_KEY",
            "OLLAMA_BASE_URL",
            keyless=True,
        ),
        Provider(
            "llamacpp",
            "llama.cpp server (local)",
            "http://localhost:8080/v1",
            "local",
            "LLAMACPP_API_KEY",
            "LLAMACPP_BASE_URL",
            keyless=True,
        ),
        Provider(
            "mimo",
            "Xiaomi MiMo",
            "https://token-plan-sgp.xiaomimimo.com/v1",
            "mimo-v2.5-pro",
            "MIMO_API_KEY",
            "MIMO_BASE_URL",
            auth_style="api-key",
        ),
        Provider(
            "custom",
            "Any OpenAI-compatible endpoint",
            "",  # must be supplied: CREWFORGE_BASE_URL or --base-url
            "",  # must be supplied: CREWFORGE_MODEL or --model
            ENV_API_KEY,
            ENV_BASE_URL,
            keyless=True,  # many self-hosted servers need no key
        ),
    )
}


def get_provider(name: str) -> Provider | None:
    """Return the preset called ``name`` (case-insensitive), or ``None``."""
    return PROVIDERS.get((name or "").strip().lower())


def provider_names() -> list[str]:
    return list(PROVIDERS)
