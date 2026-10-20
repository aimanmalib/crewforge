"""Aggregate metrics across several scaffold runs (from apiforge)."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineMetric:
    """Single pipeline run metric."""

    run_id: str
    description_length: int
    endpoints_generated: int
    models_generated: int
    validation_score: int
    total_tokens: int
    total_calls: int
    duration_seconds: float
    framework: str
    auth_type: str
    timestamp: float = field(default_factory=time.time)


class PipelineAnalytics:
    """Track and analyze pipeline runs over time."""

    def __init__(self) -> None:
        self._metrics: list[PipelineMetric] = []

    def record(self, metric: PipelineMetric) -> None:
        """Record a pipeline run metric."""
        self._metrics.append(metric)

    @property
    def total_runs(self) -> int:
        return len(self._metrics)

    def average_score(self) -> float:
        """Average validation score across all runs."""
        if not self._metrics:
            return 0.0
        return sum(m.validation_score for m in self._metrics) / len(self._metrics)

    def average_tokens(self) -> float:
        """Average tokens per run."""
        if not self._metrics:
            return 0.0
        return sum(m.total_tokens for m in self._metrics) / len(self._metrics)

    def average_duration(self) -> float:
        """Average run duration in seconds."""
        if not self._metrics:
            return 0.0
        return sum(m.duration_seconds for m in self._metrics) / len(self._metrics)

    def total_tokens_consumed(self) -> int:
        return sum(m.total_tokens for m in self._metrics)

    def total_api_calls(self) -> int:
        return sum(m.total_calls for m in self._metrics)

    def framework_breakdown(self) -> dict[str, int]:
        """Count of runs per framework."""
        counts: dict[str, int] = defaultdict(int)
        for m in self._metrics:
            counts[m.framework] += 1
        return dict(counts)

    def auth_type_breakdown(self) -> dict[str, int]:
        """Count of runs per auth type."""
        counts: dict[str, int] = defaultdict(int)
        for m in self._metrics:
            counts[m.auth_type] += 1
        return dict(counts)

    def top_runs(self, n: int = 5) -> list[PipelineMetric]:
        """Top N runs by validation score."""
        return sorted(self._metrics, key=lambda m: m.validation_score, reverse=True)[:n]

    def summary(self) -> dict[str, Any]:
        """Full analytics summary."""
        return {
            "total_runs": self.total_runs,
            "average_score": round(self.average_score(), 1),
            "average_tokens": round(self.average_tokens(), 0),
            "average_duration_seconds": round(self.average_duration(), 2),
            "total_tokens_consumed": self.total_tokens_consumed(),
            "total_api_calls": self.total_api_calls(),
            "framework_breakdown": self.framework_breakdown(),
            "auth_type_breakdown": self.auth_type_breakdown(),
            "top_scores": [m.validation_score for m in self.top_runs()],
        }

    def reset(self) -> None:
        self._metrics.clear()
