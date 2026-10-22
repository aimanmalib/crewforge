"""LLM connection settings and the optional ``crewforge.yaml`` file.

Resolution order for each connection field (first non-empty wins):

1. an explicit value (constructor argument, CLI flag or YAML file)
2. the generic ``CREWFORGE_API_KEY`` / ``CREWFORGE_BASE_URL`` / ``CREWFORGE_MODEL``
3. the provider's own variables, e.g. ``OPENAI_API_KEY`` / ``OPENAI_BASE_URL``
4. the preset default

Secrets are only ever read from the environment (or from a YAML ``${VAR}``
reference that is expanded at load time). Nothing in this module writes a key
to disk: :meth:`Settings.to_template` emits ``${VAR}`` references instead.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .errors import ConfigError
from .providers import (
    DEFAULT_PROVIDER,
    ENV_API_KEY,
    ENV_BASE_URL,
    ENV_MODEL,
    ENV_PROVIDER,
    PROVIDERS,
    get_provider,
)

_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def expand_env(value: Any) -> Any:
    """Recursively expand ``${VAR}`` references from the environment.

    An unset variable expands to an empty string, so a missing key is reported
    by :meth:`LLMConfig.validate` instead of being sent literally as the key.
    """
    if isinstance(value, str):
        return _ENV_REF.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, dict):
        return {k: expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_env(v) for v in value]
    return value


class LLMConfig(BaseModel):
    """Connection settings for one OpenAI-compatible chat completions endpoint."""

    model_config = ConfigDict(validate_assignment=False)

    provider: str = ""
    # repr=False keeps the key out of logs, tracebacks and ``print(config)``.
    api_key: str = Field(default="", repr=False)
    base_url: str = ""
    model: str = ""
    auth_style: str = ""  # "bearer" | "api-key"; blank = provider default
    temperature: float = 0.3
    max_tokens: int = 4096
    timeout: float = 120.0  # seconds, per HTTP attempt
    max_retries: int = 3  # total attempts for 429 / 5xx / network errors
    retry_delay: float = 1.0  # base delay for exponential backoff (seconds)
    max_retry_delay: float = 30.0

    @model_validator(mode="after")
    def _resolve(self) -> LLMConfig:
        self.provider = (self.provider or os.environ.get(ENV_PROVIDER) or DEFAULT_PROVIDER).lower()
        preset = get_provider(self.provider)
        env_key = preset.env_key if preset else ENV_API_KEY
        env_base = preset.env_base if preset else ENV_BASE_URL
        if not self.api_key:
            self.api_key = os.environ.get(ENV_API_KEY) or os.environ.get(env_key, "")
        if not self.base_url:
            self.base_url = (
                os.environ.get(ENV_BASE_URL)
                or os.environ.get(env_base)
                or (preset.base_url if preset else "")
            )
        self.base_url = self.base_url.rstrip("/")
        if not self.model:
            self.model = os.environ.get(ENV_MODEL) or (preset.default_model if preset else "")
        if not self.auth_style:
            self.auth_style = preset.auth_style if preset else "bearer"
        return self

    @property
    def preset(self):
        return get_provider(self.provider)

    @property
    def key_env_var(self) -> str:
        """The variable a user should set to provide the key for this provider."""
        preset = self.preset
        return preset.env_key if preset else ENV_API_KEY

    @property
    def headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            if self.auth_style == "api-key":
                headers["api-key"] = self.api_key
            else:
                headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def validate_config(self) -> list[str]:
        """Return human-readable problems; empty list means the config can run."""
        problems: list[str] = []
        preset = self.preset
        if preset is None:
            problems.append(
                f"unknown provider '{self.provider}'. Known: {', '.join(PROVIDERS)} "
                "(use 'custom' with --base-url for any other OpenAI-compatible server)"
            )
        if not self.base_url:
            problems.append(f"no base URL: set {ENV_BASE_URL} or pass --base-url")
        if not self.model:
            problems.append(f"no model: set {ENV_MODEL} or pass --model")
        if not self.api_key and not (preset and preset.keyless):
            problems.append(f"no API key: set {self.key_env_var} (or {ENV_API_KEY})")
        if self.auth_style not in ("bearer", "api-key"):
            problems.append(f"auth_style must be 'bearer' or 'api-key', not '{self.auth_style}'")
        if self.max_retries < 1:
            problems.append("max_retries must be >= 1 (it counts total attempts)")
        if self.timeout <= 0:
            problems.append("timeout must be > 0 seconds")
        return problems

    def require_valid(self) -> LLMConfig:
        """Raise :class:`ConfigError` listing every problem, or return ``self``."""
        problems = self.validate_config()
        if problems:
            raise ConfigError("; ".join(problems))
        return self

    def public_dict(self) -> dict[str, Any]:
        """Settings safe to print or save: the key is replaced by its env reference."""
        data = self.model_dump()
        data["api_key"] = "${" + self.key_env_var + "}"
        return data


class Settings(BaseModel):
    """Root of ``crewforge.yaml``: one ``llm`` block plus per-recipe sections."""

    llm: LLMConfig = Field(default_factory=LLMConfig)
    review: dict[str, Any] = Field(default_factory=dict)
    docs: dict[str, Any] = Field(default_factory=dict)
    api: dict[str, Any] = Field(default_factory=dict)
    content: dict[str, Any] = Field(default_factory=dict)
    academic: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: str | Path) -> Settings:
        try:
            data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise ConfigError(f"cannot read config {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise ConfigError(f"config {path} must be a mapping at the top level")
        return cls(**expand_env(data))

    def to_template(self) -> dict[str, Any]:
        """Dict safe to write to disk: secrets are ``${VAR}`` references, never values."""
        data = self.model_dump()
        data["llm"] = self.llm.public_dict()
        return data

    def write_template(self, path: str | Path) -> Path:
        out = Path(path)
        out.write_text(
            yaml.safe_dump(self.to_template(), sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        return out
