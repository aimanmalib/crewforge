"""Usage accounting only ever reflects provider-reported numbers."""

from __future__ import annotations

import json

from crewforge.core.client import Usage
from crewforge.core.usage import UsageTracker


def reported(p, c, cached=0):
    return Usage(p, c, p + c, cached, reported=True)


def test_records_per_agent_and_totals():
    t = UsageTracker()
    t.record("security", reported(100, 20), 50)
    t.record("security", reported(10, 5), 30)
    t.record("style", reported(1, 1), 10)
    assert t.total_tokens == 137 and t.total_calls == 3
    sec = t.by_agent()["security"]
    assert (sec.calls, sec.prompt_tokens, sec.completion_tokens) == (2, 110, 25)
    assert sec.avg_latency_ms == 40


def test_unreported_usage_is_counted_as_unknown_not_zero_tokens():
    t = UsageTracker()
    t.record("writer", Usage(), 10)  # provider sent no usage
    t.record("writer", None, 10)
    assert t.total_tokens == 0
    assert t.unreported_calls == 2
    assert "2 call(s) returned no usage" in t.one_line()


def test_errors_are_counted_without_tokens():
    t = UsageTracker()
    t.record("parser", None, 5, error=True)
    assert t.errors == 1 and t.total_tokens == 0 and t.unreported_calls == 0


def test_summary_and_save(tmp_path):
    t = UsageTracker()
    t.record("a", reported(3, 4, cached=2), 12.345)
    t.finish()
    path = t.save(tmp_path / "m" / "usage.json")
    data = json.loads(path.read_text())
    assert data["total_tokens"] == 7 and data["calls"] == 1
    assert data["agents"]["a"]["cached_tokens"] == 2
    assert data["agents"]["a"]["avg_latency_ms"] == 12.3
    assert t.duration_s >= 0
