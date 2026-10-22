"""Settings for the academic recipe (the ``academic:`` section of ``crewforge.yaml``)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ...core.errors import ConfigError
from .agents import STYLES
from .language import LANGUAGES


class AcademicSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: str = "en"  # output language: en | ms
    citation_style: str = "apa"  # apa | ieee | harvard
    log_file: str = "crewforge-academic-log.jsonl"  # record read by `disclose`
    max_input_chars: int = Field(default=60_000, gt=0)  # longest brief/draft accepted
    max_suggestion_words: int = Field(default=60, gt=0)  # feedback comments, not rewrites

    @field_validator("language")
    @classmethod
    def _language(cls, value: str) -> str:
        if value not in LANGUAGES:
            raise ValueError(f"must be one of {', '.join(LANGUAGES)}")
        return value

    @field_validator("citation_style")
    @classmethod
    def _style(cls, value: str) -> str:
        value = value.lower()
        if value not in STYLES:
            raise ValueError(f"must be one of {', '.join(STYLES)}")
        return value

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> AcademicSettings:
        """Build from the YAML ``academic:`` section; any problem is a :class:`ConfigError`."""
        try:
            return cls(**(data or {}))
        except ValidationError as exc:
            first = exc.errors()[0]
            loc = ".".join(str(p) for p in first.get("loc", ()))
            raise ConfigError(f"academic.{loc}: {first.get('msg')}") from exc
