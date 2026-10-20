"""Settings for the content recipe (the ``content:`` section of crewforge.yaml)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

PUBLISH_TARGETS = ("markdown", "html", "json")


class PipelineConfig(BaseModel):
    topic: str = ""
    target_word_count: int = 2000
    language: str = "en"
    seo_enabled: bool = True
    quality_threshold: float = 0.8  # fraction of 100
    max_iterations: int = 3  # editor <-> quality rounds
    accept_below_threshold: bool = False
    enable_translation: bool = False
    target_languages: list[str] = Field(default_factory=lambda: ["zh", "ms"])
    publish_targets: list[str] = Field(default_factory=lambda: ["markdown"])

    @field_validator("quality_threshold")
    @classmethod
    def _threshold_range(cls, v: float) -> float:
        if not 0 <= v <= 1:
            raise ValueError("quality_threshold is a fraction between 0 and 1")
        return v

    @field_validator("max_iterations")
    @classmethod
    def _iterations_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("max_iterations must be >= 1")
        return v


class AgentConfig(BaseModel):
    """Per-agent overrides (model, sampling, system prompt)."""

    name: str
    enabled: bool = True
    model_override: str | None = None
    temperature_override: float | None = None
    max_tokens_override: int | None = None
    system_prompt_override: str | None = None


class ContentSettings(BaseModel):
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    agents: list[AgentConfig] = Field(default_factory=list)
    output_dir: str = "./output"

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> ContentSettings:
        return cls(**(data or {}))

    def get_agent_config(self, name: str) -> AgentConfig:
        for agent in self.agents:
            if agent.name == name:
                return agent
        return AgentConfig(name=name)
