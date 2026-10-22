"""The AI-use record and the disclosure statement built from it (no LLM).

Every ``plan`` / ``feedback`` / ``cite`` run appends one JSON line to a log
file describing what the tool did: the step, the date, the model, the input
file names with a SHA-256 of their content (never the content itself, never a
key or URL), and counts. ``disclose`` turns that log into a statement. Because
the statement is generated from the record and fixed locale text, it can only
claim what actually happened.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from ... import __version__
from ...core.config import LLMConfig
from .language import format_date, locale, style_name, t

TOOL = "crewforge academic"
STEPS = ("plan", "feedback", "cite")
RECORD_VERSION = 1


class DisclosureError(ValueError):
    """The usage log cannot be read as a record of AI use."""


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_record(
    step: str,
    *,
    config: LLMConfig,
    language: str,
    inputs: list[tuple[str, str]],
    counts: dict[str, int],
    style: str | None = None,
    tokens: int = 0,
    now: datetime | None = None,
) -> dict[str, Any]:
    """One log entry. ``inputs`` are ``(file name, content)``; only the hash is kept."""
    if step not in STEPS:
        raise ValueError(f"unknown step {step!r}")
    return {
        "v": RECORD_VERSION,
        "ts": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
        "tool": TOOL,
        "version": __version__,
        "step": step,
        "provider": config.provider,
        "model": config.model,
        "language": language,
        "style": style,
        "inputs": [{"name": Path(name).name, "sha256": sha256(text)} for name, text in inputs],
        "counts": dict(counts),
        "tokens": tokens,
    }


def append_record(path: str | Path, record: dict[str, Any]) -> Path:
    out = Path(path)
    if out.parent and not out.parent.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return out


def read_records(path: str | Path) -> list[dict[str, Any]]:
    """Read the log. A corrupt line is an error naming the line, never skipped."""
    records = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DisclosureError(f"{path}:{number}: not a JSON record ({exc.msg})") from exc
        if not isinstance(record, dict) or record.get("step") not in STEPS or "ts" not in record:
            raise DisclosureError(f"{path}:{number}: not a {TOOL} usage record")
        records.append(record)
    return records


@dataclass
class StepSummary:
    """All runs of one step, merged."""

    step: str
    dates: list[date] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    styles: list[str] = field(default_factory=list)
    runs: int = 0


def summarise(records: list[dict[str, Any]]) -> list[StepSummary]:
    by_step: dict[str, StepSummary] = {}
    for r in records:
        s = by_step.setdefault(r["step"], StepSummary(r["step"]))
        s.runs += 1
        day = datetime.fromisoformat(r["ts"]).date()
        if day not in s.dates:
            s.dates.append(day)
        for item in r.get("inputs") or []:
            if item.get("name") and item["name"] not in s.inputs:
                s.inputs.append(item["name"])
        for key, value in (r.get("counts") or {}).items():
            s.counts[key] = s.counts.get(key, 0) + int(value or 0)
        if r.get("style") and r["style"] not in s.styles:
            s.styles.append(r["style"])
    for s in by_step.values():
        s.dates.sort()
    return [by_step[step] for step in STEPS if step in by_step]


def _models(records: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for r in records:
        label = f"{r.get('model') or '?'} ({r.get('provider') or '?'})"
        if label not in out:
            out.append(label)
    return out


def _step_line(s: StepSummary, lang: str) -> str:
    counts = {
        k: s.counts.get(k, 0)
        for k in (
            "research_questions",
            "sections",
            "suggested_readings",
            "flagged_readings",
            "comments",
            "references",
        )
    }
    inputs = ", ".join(s.inputs) or "-"
    styles = ", ".join(style_name(lang, x) for x in s.styles) or "-"
    text = t(lang, f"disclosure.steps.{s.step}", inputs=inputs, style=styles, **counts)
    if s.step == "plan" and counts["suggested_readings"]:
        text += " " + t(lang, "disclosure.steps.plan_readings", **counts)
        if counts["flagged_readings"]:
            text += " " + t(lang, "disclosure.steps.plan_readings_flagged", **counts)
    dates = ", ".join(format_date(lang, d) for d in s.dates)
    return f"- {dates}: {text}"


def build_statement(records: list[dict[str, Any]], lang: str) -> str:
    """The AI-use statement in Markdown. ``records`` must not be empty."""
    if not records:
        raise DisclosureError("no records")
    versions = sorted({str(r.get("version") or "?") for r in records})
    lines = [
        f"## {t(lang, 'disclosure.heading')}",
        "",
        t(
            lang,
            "disclosure.intro",
            tool=TOOL,
            version=", ".join(versions),
            models=", ".join(_models(records)),
        ),
        "",
        *(_step_line(s, lang) for s in summarise(records)),
        "",
        t(lang, "disclosure.tool_limits"),
        "",
        f"### {t(lang, 'disclosure.checklist_heading')}",
        "",
        *(f"- [ ] {item}" for item in _checklist(lang)),
    ]
    return "\n".join(lines) + "\n"


def _checklist(lang: str) -> list[str]:
    return list(locale(lang)["disclosure"]["checklist"])
