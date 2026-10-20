"""Text helpers for the content recipe.

JSON extraction lives in the core (:func:`crewforge.core.extract_json`); it is
re-exported here because contentforge exposed it from its text utilities.
"""

from __future__ import annotations

import re

from ...core.parsing import extract_json

__all__ = [
    "extract_frontmatter",
    "extract_json",
    "reading_time",
    "slugify",
    "truncate",
    "word_count",
]


def word_count(text: str) -> int:
    """Count words; each CJK character counts as one word."""
    cjk = len(re.findall(r"[一-鿿㐀-䶿]", text))
    english_words = len(re.findall(r"[a-zA-Z]+", text))
    return cjk + english_words


def extract_frontmatter(text: str) -> tuple[dict, str]:
    """Split YAML front matter from a Markdown document."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            import yaml

            fm = yaml.safe_load(parts[1]) or {}
            return fm, parts[2].strip()
    return {}, text


def truncate(text: str, max_chars: int = 100, suffix: str = "...") -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - len(suffix)] + suffix


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text.strip("-")


def reading_time(text: str, wpm: int = 200) -> str:
    minutes = max(1, round(word_count(text) / wpm))
    return f"{minutes} min read"
