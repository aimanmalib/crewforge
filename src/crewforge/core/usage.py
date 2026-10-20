"""Per-agent usage accounting built only from provider-reported numbers."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .client import Usage


@dataclass
class AgentUsage:
    agent: str
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0
    unreported_calls: int = 0  # calls whose response carried no usage object
    errors: int = 0
    retries: int = 0  # extra HTTP attempts (429/5xx/network) behind these calls
    latency_ms: float = 0.0

    @property
    def avg_latency_ms(self) -> float:
        return self.latency_ms / self.calls if self.calls else 0.0

    @property
    def tokens_per_call(self) -> float:
        return self.total_tokens / self.calls if self.calls else 0.0

    @property
    def cache_hit_rate(self) -> float:
        """Share of prompt tokens the provider reported as served from its cache."""
        return self.cached_tokens / self.prompt_tokens if self.prompt_tokens else 0.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["avg_latency_ms"] = round(self.avg_latency_ms, 1)
        data["tokens_per_call"] = round(self.tokens_per_call, 1)
        data["cache_hit_rate"] = round(self.cache_hit_rate, 3)
        data["latency_ms"] = round(self.latency_ms, 1)
        return data


class UsageTracker:
    """Collects what each agent cost, as reported by the provider."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentUsage] = {}
        self._started = time.monotonic()
        self._ended: float | None = None
        self.run_id = time.strftime("%Y%m%d_%H%M%S")

    def record(
        self,
        agent: str,
        usage: Usage | None,
        latency_ms: float = 0.0,
        *,
        error: bool = False,
        retries: int = 0,
    ) -> None:
        entry = self._agents.setdefault(agent, AgentUsage(agent))
        entry.calls += 1
        entry.latency_ms += latency_ms
        entry.retries += retries
        if error:
            entry.errors += 1
            return
        if usage is None or not usage.reported:
            entry.unreported_calls += 1
            return
        entry.prompt_tokens += usage.prompt_tokens
        entry.completion_tokens += usage.completion_tokens
        entry.total_tokens += usage.total_tokens
        entry.cached_tokens += usage.cached_tokens

    def reset(self) -> None:
        """Forget everything recorded so far and restart the clock."""
        self._agents.clear()
        self._started = time.monotonic()
        self._ended = None

    def finish(self) -> None:
        self._ended = time.monotonic()

    def by_agent(self) -> dict[str, AgentUsage]:
        return dict(self._agents)

    @property
    def total_tokens(self) -> int:
        return sum(a.total_tokens for a in self._agents.values())

    @property
    def prompt_tokens(self) -> int:
        return sum(a.prompt_tokens for a in self._agents.values())

    @property
    def completion_tokens(self) -> int:
        return sum(a.completion_tokens for a in self._agents.values())

    @property
    def total_calls(self) -> int:
        return sum(a.calls for a in self._agents.values())

    @property
    def unreported_calls(self) -> int:
        return sum(a.unreported_calls for a in self._agents.values())

    @property
    def errors(self) -> int:
        return sum(a.errors for a in self._agents.values())

    @property
    def duration_s(self) -> float:
        return (self._ended or time.monotonic()) - self._started

    def summary(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "duration_s": round(self.duration_s, 2),
            "calls": self.total_calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "unreported_calls": self.unreported_calls,
            "errors": self.errors,
            "agents": {name: a.to_dict() for name, a in self._agents.items()},
        }

    def one_line(self) -> str:
        """e.g. ``7 LLM calls · 12,345 tokens (provider-reported) · 21.4s``."""
        text = (
            f"{self.total_calls} LLM call(s) · {self.total_tokens:,} tokens "
            f"(provider-reported) · {self.duration_s:.1f}s"
        )
        if self.unreported_calls:
            text += f" · {self.unreported_calls} call(s) returned no usage (not counted)"
        return text

    def report(self) -> str:
        """Plain-text per-agent table (for logs and non-terminal output)."""
        lines = [
            f"Token usage — run {self.run_id} (provider-reported)",
            f"{'agent':<16}{'calls':>6}{'prompt':>10}{'completion':>12}{'total':>10}{'ms/call':>9}",
        ]
        for a in self._agents.values():
            lines.append(
                f"{a.agent:<16}{a.calls:>6}{a.prompt_tokens:>10,}{a.completion_tokens:>12,}"
                f"{a.total_tokens:>10,}{a.avg_latency_ms:>9.0f}"
            )
        lines.append(self.one_line())
        return "\n".join(lines)

    def save(self, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(self.summary(), indent=2), encoding="utf-8")
        return out
