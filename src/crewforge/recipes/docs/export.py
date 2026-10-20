"""Export a Q&A session to Markdown or JSON (deterministic, no LLM calls)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agents import Answer, FactCheckResult


class ExportAgent:
    """Write the answers of a session (with citations and verdicts) to a file."""

    name = "export"

    def __init__(self) -> None:
        # Fact-check results keyed by id(answer), filled in by the pipeline.
        self.checks: dict[int, FactCheckResult] = {}

    def _format_markdown(self, answers: list[Answer], title: str = "crewforge Q&A session") -> str:
        """Format answers as a Markdown document."""
        lines = [
            f"# {title}",
            "",
            f"*Generated on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*",
            f"*Total questions: {len(answers)}*",
            "",
            "---",
            "",
        ]

        for i, answer in enumerate(answers, 1):
            lines.append(f"## Q{i}: {answer.question}")
            lines.append("")
            lines.append(answer.answer_text)
            lines.append("")
            if answer.citations:
                lines.append("**Sources:**")
                for c in answer.citations:
                    lines.append(
                        f"- [Source {c['source_num']}] {c.get('document_id', 'N/A')} "
                        f"— {c.get('excerpt', '')[:150]}..."
                    )
                lines.append("")
            lines.append(f"*Confidence: {answer.confidence}*")
            check = self.checks.get(id(answer))
            if check is not None:
                lines.append(
                    f"*Verification: {check.overall_verdict} "
                    f"({check.claims_verified}/{check.claims_checked} claims verified)*"
                )
            lines.append("")
            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    def _format_json(self, answers: list[Answer]) -> str:
        """Format answers as JSON."""
        data = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "total_questions": len(answers),
            "answers": [
                {
                    "question": a.question,
                    "answer": a.answer_text,
                    "citations": a.citations,
                    "confidence": a.confidence,
                    "verification": (
                        {
                            "verdict": self.checks[id(a)].overall_verdict,
                            "claims_checked": self.checks[id(a)].claims_checked,
                            "claims_verified": self.checks[id(a)].claims_verified,
                            "issues": self.checks[id(a)].issues,
                        }
                        if id(a) in self.checks
                        else None
                    ),
                }
                for a in answers
            ],
        }
        return json.dumps(data, indent=2, ensure_ascii=False)

    async def export_session(
        self,
        answers: list[Answer],
        output_path: str | Path,
        *,
        format: str = "markdown",
        title: str = "crewforge Q&A session",
    ) -> Path:
        """Export a Q&A session to file."""
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)

        if format == "json":
            content = self._format_json(answers)
            if not p.suffix:
                p = p.with_suffix(".json")
        else:
            content = self._format_markdown(answers, title)
            if not p.suffix:
                p = p.with_suffix(".md")

        p.write_text(content, encoding="utf-8")
        return p

    async def run(self, **kwargs: Any) -> Path:
        """Run export. Expects 'answers' and 'output_path'."""
        return await self.export_session(
            kwargs["answers"],
            kwargs["output_path"],
            format=kwargs.get("format", "markdown"),
            title=kwargs.get("title", "crewforge Q&A session"),
        )
