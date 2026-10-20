"""Content pipeline: research → outline → write → SEO → (edit ↔ quality) → translate → publish.

Every step runs through ``Crew.step``, so an agent that errors or returns
nothing stops the run naming itself — contentforge never checked the writer,
SEO, editor or translator results. A quality score that never reaches the
threshold is also a failure unless ``accept_below_threshold`` is set.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from ...core.client import LLMClient
from ...core.config import LLMConfig
from ...core.crew import Crew
from ...core.errors import AgentFailure, CrewFailedError
from ...core.usage import UsageTracker
from .agents import AGENT_REGISTRY, AgentResult, ContentAgent
from .settings import ContentSettings

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Final result from the complete pipeline."""

    status: str = "success"  # success | below_threshold
    article: str = ""
    research: str = ""
    outline: str = ""
    seo_analysis: str = ""
    quality_report: str = ""
    quality_score: float | None = None
    publisher_output: str = ""
    output_files: list[str] = field(default_factory=list)
    translations: dict[str, str] = field(default_factory=dict)
    agent_results: dict[str, AgentResult] = field(default_factory=dict)
    metrics_path: str = ""
    total_tokens: int = 0
    pipeline_duration_s: float = 0.0
    tracker: UsageTracker | None = field(default=None, repr=False)

    @property
    def ok(self) -> bool:
        return self.status == "success"

    def summary(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "total_tokens": self.total_tokens,
            "pipeline_duration_s": round(self.pipeline_duration_s, 2),
            "agents_run": list(self.agent_results.keys()),
            "article_length": len(self.article),
            "word_count": len(self.article.split()),
            "quality_score": self.quality_score,
            "translations": list(self.translations.keys()),
            "output_files": self.output_files,
            "metrics_path": self.metrics_path,
        }


class ContentPipeline:
    """Coordinates the eight content agents on one crew."""

    AGENT_ORDER = list(AGENT_REGISTRY)

    def __init__(
        self,
        llm: LLMConfig,
        settings: ContentSettings | None = None,
        *,
        client: LLMClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.llm = llm
        self.settings = settings or ContentSettings()
        self._client = client
        self._transport = transport

    def _agent(self, crew: Crew, name: str) -> ContentAgent:
        return AGENT_REGISTRY[name](crew.client, crew.tracker, config=self.settings)

    async def _step(self, crew: Crew, result: PipelineResult, key: str, agent, **kwargs):
        out: AgentResult = await crew.step(key, agent.execute(**kwargs))
        if not out.content.strip():  # defence in depth; ask() already refuses blanks
            failure = AgentFailure(key, "returned empty output", "empty")
            raise CrewFailedError(crew.name, [failure])
        result.agent_results[key] = out
        return out

    async def run(self, topic: str) -> PipelineResult:
        cfg = self.settings.pipeline
        result = PipelineResult()
        crew = Crew("content", self.llm, client=self._client, transport=self._transport)
        try:
            async with crew:
                research = await self._step(
                    crew, result, "research", self._agent(crew, "research"), topic=topic
                )
                result.research = research.content

                outline = await self._step(
                    crew,
                    result,
                    "outline",
                    self._agent(crew, "outline"),
                    research_data=research.content,
                    target_words=cfg.target_word_count,
                )
                result.outline = outline.content

                draft = await self._step(
                    crew,
                    result,
                    "writer",
                    self._agent(crew, "writer"),
                    outline=outline.content,
                    research_data=research.content,
                    language=cfg.language,
                )
                current = draft.content

                seo_notes = ""
                if cfg.seo_enabled:
                    seo = await self._step(
                        crew, result, "seo", self._agent(crew, "seo"), content=current
                    )
                    result.seo_analysis = seo_notes = seo.content

                threshold = cfg.quality_threshold * 100
                for iteration in range(cfg.max_iterations):
                    edited = await self._step(
                        crew,
                        result,
                        "editor",
                        self._agent(crew, "editor"),
                        content=current,
                        seo_recommendations=seo_notes,
                    )
                    current = edited.content
                    quality = await self._step(
                        crew,
                        result,
                        "quality",
                        self._agent(crew, "quality"),
                        content=current,
                        threshold=cfg.quality_threshold,
                        title=topic,
                    )
                    result.quality_report = quality.content
                    result.quality_score = quality.metadata["overall_score"]
                    if result.quality_score >= threshold:
                        break
                    logger.info(
                        "[content] quality %.0f < %.0f (iteration %d/%d)",
                        result.quality_score,
                        threshold,
                        iteration + 1,
                        cfg.max_iterations,
                    )
                result.article = current

                if result.quality_score is not None and result.quality_score < threshold:
                    message = (
                        f"final quality score {result.quality_score:.0f} is below the "
                        f"threshold {threshold:.0f} after {cfg.max_iterations} edit round(s)"
                    )
                    if not cfg.accept_below_threshold:
                        failure = AgentFailure("quality", message, "below_threshold")
                        crew.failures.append(failure)
                        raise CrewFailedError(crew.name, [failure])
                    result.status = "below_threshold"

                if cfg.enable_translation and cfg.target_languages:
                    work = {
                        f"translator_{lang}": self._agent(crew, "translator").execute(
                            content=current, target_language=lang, source_language=cfg.language
                        )
                        for lang in cfg.target_languages
                    }
                    for key, out in (await crew.parallel(work)).items():
                        if not out.content.strip():
                            raise CrewFailedError(
                                crew.name, [AgentFailure(key, "returned empty output", "empty")]
                            )
                        result.agent_results[key] = out
                        result.translations[key.removeprefix("translator_")] = out.content

                publisher = await self._step(
                    crew,
                    result,
                    "publisher",
                    self._agent(crew, "publisher"),
                    content=current,
                    title=topic,
                    publish_targets=cfg.publish_targets,
                    output_dir=self.settings.output_dir,
                    language=cfg.language,
                )
                result.publisher_output = publisher.content
                result.output_files = list(publisher.metadata.get("output_files", []))
                out_dir = Path(self.settings.output_dir)
                for lang, text in result.translations.items():
                    path = out_dir / f"translation.{lang}.md"
                    path.write_text(text, encoding="utf-8")
                    result.output_files.append(str(path))
        finally:
            result.tracker = crew.tracker
            result.total_tokens = crew.tracker.total_tokens
            result.pipeline_duration_s = crew.tracker.duration_s
        metrics = Path(self.settings.output_dir) / "metrics" / f"{crew.tracker.run_id}.json"
        result.metrics_path = str(crew.tracker.save(metrics))
        return result

    def get_agent_list(self) -> list[dict[str, str]]:
        return [{"name": n, "description": c.description} for n, c in AGENT_REGISTRY.items()]
