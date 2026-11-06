"""Render a :class:`ReviewResult` as JSON, SARIF or Markdown."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ... import __version__
from .agents import SEVERITIES
from .pipeline import ReviewResult
from .sources import Sources

SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
#: Finding severity -> SARIF ``level`` (GitHub code scanning shows error/warning/note).
SARIF_LEVELS = {"critical": "error", "error": "error", "warning": "warning", "info": "note"}


def report_dict(result: ReviewResult) -> dict[str, Any]:
    """Machine-readable report: decision, per-agent findings/status, usage."""
    summary = result.summary_result
    return {
        "status": result.status,
        "language": result.language or "auto",
        "decision": (summary.data.get("decision") if summary else None),
        "quality_score": (summary.data.get("quality_score") if summary else None),
        "total_findings": result.total_findings,
        "total_tokens": result.total_tokens,
        "duration_s": round(result.duration_s, 2),
        "agents": {
            name: {
                "status": r.status,
                "summary": r.summary,
                "findings": r.findings,
                "tokens": r.tokens_used,
                "error": r.error,
            }
            for name, r in result.agent_results.items()
        },
        "summary": (
            {
                "status": summary.status,
                "report": summary.summary,
                "top_issues": summary.data.get("top_issues", []),
                "error": summary.error,
            }
            if summary
            else None
        ),
        "usage": result.usage,
    }


def _finding_line(agent: str, f: dict[str, Any]) -> str:
    where = f" (line {f['line']})" if f.get("line") not in (None, "") else ""
    cwe = f" [{f['cwe']}]" if f.get("cwe") else ""
    text = f"- **{f.get('title') or 'Untitled'}**{where}{cwe} — _{agent}_"
    if f.get("description"):
        text += f": {f['description']}"
    if f.get("suggestion"):
        text += f"\n  - Fix: {f['suggestion']}"
    return text


def report_markdown(result: ReviewResult) -> str:
    """Human-readable Markdown report."""
    lines = ["# crewforge review", ""]
    summary = result.summary_result
    if summary and summary.ok:
        lines += [
            f"**Decision:** {summary.data.get('decision')} · "
            f"**Quality score:** {summary.data.get('quality_score')}/100",
            "",
        ]
        if summary.summary.strip():
            lines += ["## Summary", "", summary.summary.strip(), ""]
        top = summary.data.get("top_issues") or []
        if top:
            lines += ["### Top issues", ""] + [f"{i}. {t}" for i, t in enumerate(top, 1)] + [""]
    elif summary:
        lines += ["## Summary", "", f"_Summary agent failed: {summary.error}_", ""]

    lines += ["## Findings", ""]
    any_finding = False
    for severity in SEVERITIES:
        rows = [
            _finding_line(name, f)
            for name, r in result.agent_results.items()
            for f in r.findings
            if f.get("severity") == severity
        ]
        if rows:
            any_finding = True
            lines += [f"### {severity.capitalize()} ({len(rows)})", ""] + rows + [""]
    if not any_finding:
        lines += ["_No findings reported._", ""]

    lines += ["## Reviewers", ""]
    for name, r in result.agent_results.items():
        if r.ok:
            note = r.summary.strip() or "no summary"
            lines.append(f"- **{name}** ({r.finding_count} finding(s)): {note}")
        else:
            lines.append(f"- **{name}**: _Agent failed: {r.error}_")
    lines.append("")
    agents_run = len(result.agent_results) + (1 if summary else 0)
    lines.append(
        f"_Tokens: {result.total_tokens:,} (provider-reported) · "
        f"Duration: {result.duration_s:.1f}s · Agents: {agents_run}_"
    )
    return "\n".join(lines) + "\n"


def _uri(path: Path) -> str:
    """Artifact URI: relative paths stay relative (GitHub resolves them from the repo root)."""
    return path.as_uri() if path.is_absolute() else path.as_posix()


def _int_line(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        return int(value) or None
    return None


def report_sarif(result: ReviewResult, sources: Sources, target: str | Path) -> dict[str, Any]:
    """SARIF 2.1.0 log for GitHub code scanning: one ``result`` per finding.

    A finding's line refers to the text the reviewers saw. For a directory that
    is every file joined under ``# File:`` headers, so the line is mapped back to
    its file; a line that cannot be mapped keeps the reviewed path, without a region.
    """
    results: list[dict[str, Any]] = []
    rules: dict[str, dict[str, Any]] = {}
    for agent, r in result.agent_results.items():
        for f in r.findings:
            rule_id = str(f.get("cwe") or agent)
            rules.setdefault(rule_id, {"id": rule_id})
            title = str(f.get("title") or "Untitled")
            message = f"{title}: {f['description']}" if f.get("description") else title
            if f.get("suggestion"):
                message += f"\nFix: {f['suggestion']}"
            physical: dict[str, Any] = {"artifactLocation": {"uri": _uri(Path(target))}}
            line = _int_line(f.get("line"))
            spot = sources.locate(line) if line is not None else None
            if spot is not None:
                physical = {
                    "artifactLocation": {"uri": _uri(spot[0])},
                    "region": {"startLine": spot[1]},
                }
            results.append(
                {
                    "ruleId": rule_id,
                    "level": SARIF_LEVELS.get(str(f.get("severity")), "note"),
                    "message": {"text": message},
                    "locations": [{"physicalLocation": physical}],
                    "properties": {"agent": agent, "severity": f.get("severity", "info")},
                }
            )
    return {
        "$schema": SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "crewforge",
                        "version": __version__,
                        "informationUri": "https://github.com/aimanmalib/crewforge",
                        "rules": list(rules.values()),
                    }
                },
                "invocations": [
                    {
                        "executionSuccessful": not result.failed_agents,
                        "toolExecutionNotifications": [
                            {
                                "level": "error",
                                "message": {"text": f"agent '{name}' failed: {r.error}"},
                            }
                            for name, r in result.agent_results.items()
                            if not r.ok
                        ],
                    }
                ],
                "results": results,
            }
        ],
    }
