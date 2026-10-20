"""Settings for the ``docs`` recipe (the ``docs:`` section of ``crewforge.yaml``)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from ...core.errors import ConfigError

CITATION_FORMATS = ("apa", "mla", "chicago")


class DocsSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_size: int = 512  # characters per chunk
    chunk_overlap: int = 64  # characters carried into the next chunk
    retrieval_k: int = 5  # passages given to the answerer
    citation_format: str = "apa"

    def problems(self) -> list[str]:
        problems: list[str] = []
        if self.chunk_size < 64:
            problems.append("docs.chunk_size must be >= 64")
        if self.chunk_overlap < 0:
            problems.append("docs.chunk_overlap must be >= 0")
        if self.chunk_overlap >= self.chunk_size:
            problems.append("docs.chunk_overlap must be < docs.chunk_size")
        if self.retrieval_k < 1:
            problems.append("docs.retrieval_k must be >= 1")
        if self.citation_format not in CITATION_FORMATS:
            problems.append(
                f"docs.citation_format must be one of {', '.join(CITATION_FORMATS)}, "
                f"not '{self.citation_format}'"
            )
        return problems

    def require_valid(self) -> DocsSettings:
        problems = self.problems()
        if problems:
            raise ConfigError("; ".join(problems))
        return self

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> DocsSettings:
        """Build from the YAML ``docs:`` section; any problem is a :class:`ConfigError`."""
        try:
            settings = cls(**(data or {}))
        except ValidationError as exc:
            first = exc.errors()[0]
            loc = ".".join(str(p) for p in first.get("loc", ()))
            raise ConfigError(f"docs.{loc}: {first.get('msg')}") from exc
        return settings.require_valid()
