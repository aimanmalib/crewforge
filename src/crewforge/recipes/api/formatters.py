"""Output formatters for the api recipe."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class OutputFormatter:
    @staticmethod
    def to_json(data: dict[str, Any], pretty: bool = True) -> str:
        return json.dumps(data, indent=2 if pretty else None, default=str)

    @staticmethod
    def to_markdown_table(headers: list[str], rows: list[list[str]]) -> str:
        lines = ["| " + " | ".join(headers) + " |"]
        lines.append("|" + "|".join(["---"] * len(headers)) + "|")
        for row in rows:
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)

    @staticmethod
    def wrap_code(code: str, lang: str = "python") -> str:
        return f"```{lang}\n{code}\n```"

    @staticmethod
    def file_tree(files: dict[str, Path], root: Path) -> str:
        lines = [f"{root.name}/"]
        for path in sorted(files.values()):
            lines.append(f"  {path.relative_to(root)}")
        return "\n".join(lines)
