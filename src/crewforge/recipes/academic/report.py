"""Markdown and JSON renderings of plan / feedback / cite results.

Labels come from the locale files; JSON keys stay English for scripts.
"""

from __future__ import annotations

from typing import Any

from .citations import SourceCheck
from .language import style_name, t
from .pipeline import CiteResult, FeedbackResult, PlanResult


def _flag_text(lang: str, check: SourceCheck) -> list[str]:
    return [t(lang, f"flags.{code}", values=", ".join(values)) for code, values in check.flags]


def _malay(lang: str, issues: dict[str, str]) -> list[str]:
    if not issues:
        return []
    found = ", ".join(f"{k} → {v}" for k, v in issues.items())
    return ["", f"> ⚠ {t(lang, 'labels.malay_warning', found=found)}"]


# --- plan ---------------------------------------------------------------------


def plan_markdown(r: PlanResult) -> str:
    lang, b, p = r.language, r.brief, r.plan
    title = p.working_title or b.title
    lines = [f"# {t(lang, 'labels.plan_title', title=title)}", ""]
    if r.target_words:
        target = f"{r.target_words:,} {t(lang, 'labels.words_unit')}"
    else:
        target = t(lang, "labels.no_word_target")
    meta = [(t(lang, "labels.course"), b.course), (t(lang, "labels.deadline"), b.deadline)]
    meta += [
        (t(lang, "labels.target_words"), target),
        (t(lang, "labels.citation_style"), style_name(lang, r.style)),
    ]
    lines += [f"- **{k}:** {v}" for k, v in meta if v]
    if b.requirements:
        lines += ["", f"## {t(lang, 'labels.requirements')}", ""]
        lines += [f"- {x}" for x in b.requirements]
    if b.rubric:
        lines += ["", f"## {t(lang, 'labels.rubric')}", ""]
        lines += [
            f"- {x.criterion}" + (f" ({x.weight:g}%)" if x.weight is not None else "")
            for x in b.rubric
        ]
    lines += ["", f"## {t(lang, 'labels.research_questions')}", ""]
    lines += [f"{i}. {q}" for i, q in enumerate(p.research_questions, start=1)]
    lines += ["", f"## {t(lang, 'labels.outline')}", ""]
    lines += [
        f"| # | {t(lang, 'labels.section')} | {t(lang, 'labels.words')} | "
        f"{t(lang, 'labels.purpose')} |",
        "|---|---|---:|---|",
    ]
    for i, (s, words) in enumerate(zip(p.outline, r.budget, strict=True), start=1):
        lines.append(f"| {i} | {s.heading} | {words or '-'} | {s.purpose} |")
    lines += ["", t(lang, "labels.budget_total", total=f"{sum(r.budget):,}"), ""]
    for i, s in enumerate(p.outline, start=1):
        if s.key_points:
            lines.append(f"**{i}. {s.heading}**")
            lines += [f"- {k}" for k in s.key_points]
            lines.append("")
    if p.source_needs:
        lines += [f"## {t(lang, 'labels.source_needs')}", ""]
        for n in p.source_needs:
            extra = " — ".join(x for x in (n.why, n.where_to_look) if x)
            lines.append(f"- **{n.need}**" + (f" — {extra}" if extra else ""))
        lines.append("")
    if p.search_queries:
        lines += [f"## {t(lang, 'labels.search_queries')}", ""]
        lines += [f"- `{q}`" for q in p.search_queries]
        lines.append("")
    if r.readings:
        lines += [f"## {t(lang, 'labels.suggested_readings')}", ""]
        lines += [f"> {t(lang, 'labels.suggested_readings_warning')}", ""]
        for check, why in zip(r.readings, r.reading_notes, strict=True):
            lines.append(f"- ⚠ **{t(lang, f'statuses.{check.status}')}** — {check.text}")
            if why:
                lines.append(f"  - {why}")
            lines += [f"  - {f}" for f in _flag_text(lang, check)]
    lines += _malay(lang, r.malay_issues)
    return "\n".join(lines).rstrip() + "\n"


def plan_dict(r: PlanResult) -> dict[str, Any]:
    outline = [
        {**s.model_dump(), "words": words}
        for s, words in zip(r.plan.outline, r.budget, strict=True)
    ]
    return {
        "brief": r.brief.model_dump(),
        "language": r.language,
        "citation_style": r.style,
        "target_words": r.target_words,
        "working_title": r.plan.working_title,
        "research_questions": r.plan.research_questions,
        "outline": outline,
        "budget_total": sum(r.budget),
        "source_needs": [n.model_dump() for n in r.plan.source_needs],
        "search_queries": r.plan.search_queries,
        "suggested_readings": [
            {**c.to_dict(), "why": why} for c, why in zip(r.readings, r.reading_notes, strict=True)
        ],
        "malay_issues": r.malay_issues,
        "usage": r.tracker.summary() if r.tracker else {},
    }


# --- feedback -----------------------------------------------------------------


def feedback_markdown(r: FeedbackResult) -> str:
    lang = r.language
    lines = [
        f"# {t(lang, 'labels.feedback_title', name=r.name)}",
        "",
        f"> {t(lang, 'labels.feedback_note')}",
        "",
    ]
    for name, review in r.reviews.items():
        lines += [f"## {t(lang, f'reviewers.{name}')}", ""]
        if review.summary:
            lines += [review.summary, ""]
        if review.strengths:
            lines.append(f"**{t(lang, 'labels.strengths')}:**")
            lines += [f"- {s}" for s in review.strengths]
            lines.append("")
        mine = [c for c in r.comments if c.reviewer == name]
        if mine:
            lines.append(f"**{t(lang, 'labels.comments')}:**")
        for c in mine:
            where = (
                f"{t(lang, 'labels.paragraph')} {c.paragraph}"
                if c.paragraph
                else t(lang, "labels.whole_draft")
            )
            sev = t(lang, f"labels.severity_{c.severity}")
            head = f"- **{where}** ({sev})"
            if c.quote:
                head += f": “{c.quote}”"
            lines.append(head)
            lines.append(f"  - {c.issue}")
            if c.suggestion:
                lines.append(f"  - *{t(lang, 'labels.suggestion')}:* {c.suggestion}")
            lines += [f"  - ⚠ {t(lang, f'labels.{flag}')}" for flag in c.flags]
        lines.append("")
    lines += _citation_section(r)
    if r.failed:
        lines += ["", f"> ⚠ {t(lang, 'labels.failed_reviewers', names=', '.join(r.failed))}"]
    lines += _malay(lang, r.malay_issues)
    return "\n".join(lines).rstrip() + "\n"


def _citation_section(r: FeedbackResult) -> list[str]:
    lang, c = r.language, r.citations
    lines = [f"## {t(lang, 'labels.citation_check')}", ""]
    lines.append(f"- {t(lang, 'labels.in_text_found', count=len(c.in_text))}")
    if not c.has_reference_list:
        lines.append(f"- {t(lang, 'labels.no_reference_list')}")
        return lines
    lines.append(f"- {t(lang, 'labels.references_found', count=len(c.references))}")
    if c.cited_not_listed:
        lines += ["", f"**{t(lang, 'labels.cited_not_listed')}:**"]
        lines += [f"- {x}" for x in c.cited_not_listed]
    if c.listed_not_cited:
        lines += ["", f"**{t(lang, 'labels.listed_not_cited')}:**"]
        lines += [f"- {x}" for x in c.listed_not_cited]
    noted = [ref for ref in c.references if ref.flags]
    if noted:
        lines += ["", f"**{t(lang, 'labels.reference_notes')}:**"]
        for ref in noted:
            lines.append(f"- {ref.text}")
            lines += [f"  - {f}" for f in _flag_text(lang, ref)]
    return lines


def feedback_dict(r: FeedbackResult) -> dict[str, Any]:
    return {
        "name": r.name,
        "language": r.language,
        "citation_style": r.style,
        "paragraphs": r.paragraph_count,
        "reviews": {
            n: {"summary": v.summary, "strengths": v.strengths} for n, v in r.reviews.items()
        },
        "comments": [c.to_dict() for c in r.comments],
        "citation_check": r.citations.to_dict(),
        "failed": r.failed,
        "malay_issues": r.malay_issues,
        "usage": r.tracker.summary() if r.tracker else {},
    }


# --- cite ---------------------------------------------------------------------


def cite_markdown(r: CiteResult) -> str:
    lang = r.language
    lines = [
        f"# {t(lang, 'labels.cite_title', style=style_name(lang, r.style))}",
        "",
        f"> {t(lang, 'labels.cite_note')}",
        "",
    ]
    for n, ref in enumerate(r.refs, start=1):
        prefix = f"[{n}] " if r.style == "ieee" else ""
        lines.append(f"{prefix}{ref.formatted}")
        notes = []
        if ref.check.status != "supplied":
            notes.append(f"⚠ {t(lang, f'statuses.{ref.check.status}')}")
        notes += [f"⚠ {f}" for f in _flag_text(lang, ref.check)]
        if ref.missing:
            notes.append(f"{t(lang, 'labels.missing_fields')}: {', '.join(ref.missing)}")
        if ref.note:
            notes.append(ref.note)
        lines += [f"  - {x}" for x in notes]
        lines.append("")
    if r.discarded:
        lines.append(f"> ⚠ {t(lang, 'labels.discarded', count=len(r.discarded))}")
    return "\n".join(lines).rstrip() + "\n"


def cite_dict(r: CiteResult) -> dict[str, Any]:
    return {
        "citation_style": r.style,
        "language": r.language,
        "references": [
            {
                "number": n,
                "input_index": ref.index,
                "original": ref.original,
                "formatted": ref.formatted,
                "missing": ref.missing,
                "note": ref.note,
                "status": ref.check.status,
                "flags": [{"code": c, "values": v} for c, v in ref.check.flags],
            }
            for n, ref in enumerate(r.refs, start=1)
        ],
        "discarded": [d.model_dump() for d in r.discarded],
        "usage": r.tracker.summary() if r.tracker else {},
    }
