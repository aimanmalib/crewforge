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


def collect(path: str | Path, *, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES) -> Sources:
    target = Path(path)
    if target.is_file():
        code = target.read_text(encoding="utf-8", errors="replace")
        if not code.strip():
            raise SourceError(f"{target} is empty")
        return Sources(code=code, language=detect_language(target.suffix), files=[target])
    if not target.is_dir():
        raise SourceError(f"path not found: {target}")

    parts: list[str] = []
    files: list[Path] = []
    skipped: list[str] = []
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
        parts.append(f"# File: {rel}\n{text}")
        files.append(f)
        languages.add(detect_language(f.suffix))
    if not parts:
        raise SourceError(f"no supported source files found under {target}")
    language = languages.pop() if len(languages) == 1 else ""
    return Sources(code="\n\n".join(parts), language=language, files=files, skipped=skipped)
