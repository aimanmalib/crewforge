"""Collect source code to review from a file or a directory."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Map file extensions to language names for the review prompt.
EXT_TO_LANG = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cs": "csharp",
    ".kt": "kotlin",
    ".swift": "swift",
    ".scala": "scala",
    ".sh": "bash",
    ".sql": "sql",
}

#: Directories never descended into when reviewing a folder.
SKIP_DIRS = frozenset(
    {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".tox"}
)

DEFAULT_MAX_FILE_BYTES = 200_000


def detect_language(suffix: str) -> str:
    """Best-effort language detection from a file extension (``auto`` if unknown)."""
    return EXT_TO_LANG.get(suffix.lower(), "auto")


class SourceError(Exception):
    """The path cannot be reviewed (missing, empty, nothing supported)."""


@dataclass
class Sources:
    code: str
    language: str
    files: list[Path] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    #: ``(file, first, last)``: lines ``first..last`` of :attr:`code` hold line 1.. of ``file``.
    spans: list[tuple[Path, int, int]] = field(default_factory=list)

    def locate(self, line: int) -> tuple[Path, int] | None:
        """Map a line of :attr:`code` to ``(file, line in that file)``.

        ``None`` when the line is outside the code or falls on a ``# File:``
        header or the blank lines between two files.
        """
        for path, first, last in self.spans:
            if first <= line <= last:
                return path, line - first + 1
        return None


def collect(path: str | Path, *, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES) -> Sources:
    target = Path(path)
    if target.is_file():
        code = target.read_text(encoding="utf-8", errors="replace")
        if not code.strip():
            raise SourceError(f"{target} is empty")
        return Sources(
            code=code,
            language=detect_language(target.suffix),
            files=[target],
            spans=[(target, 1, _line_count(code))],
        )
    if not target.is_dir():
        raise SourceError(f"path not found: {target}")

    parts: list[str] = []
    files: list[Path] = []
    skipped: list[str] = []
    spans: list[tuple[Path, int, int]] = []
    start = 1  # line of ``code`` where the next "# File:" header goes
    languages: set[str] = set()
    for f in sorted(target.rglob("*")):
        rel = f.relative_to(target)
        if any(p in SKIP_DIRS for p in rel.parts) or not f.is_file():
            continue
        if f.suffix.lower() not in EXT_TO_LANG:
            continue
        if f.stat().st_size > max_file_bytes:
            skipped.append(f"{rel} (> {max_file_bytes} bytes)")
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        if not text.strip():
            continue
        part = f"# File: {rel}\n{text}"
        parts.append(part)
        files.append(f)
        spans.append((f, start + 1, start + _line_count(text)))
        start += part.count("\n") + 2  # the part, then the blank line joining the next one
        languages.add(detect_language(f.suffix))
    if not parts:
        raise SourceError(f"no supported source files found under {target}")
    language = languages.pop() if len(languages) == 1 else ""
    return Sources(
        code="\n\n".join(parts), language=language, files=files, skipped=skipped, spans=spans
    )


def _line_count(text: str) -> int:
    """Lines in ``text`` as an editor numbers them (a final newline adds none)."""
    return text.count("\n") + (0 if text.endswith("\n") else 1)
