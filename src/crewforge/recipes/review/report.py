"""Render a :class:`ReviewResult` as JSON or Markdown."""

from __future__ import annotations

from typing import Any

from .agents import SEVERITIES
from .pipeline import ReviewResult


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
