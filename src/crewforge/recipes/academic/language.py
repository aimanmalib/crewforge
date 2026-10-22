"""Output languages for the academic recipe: locale files and the Malay check.

All text a student reads comes from ``locales/<lang>.yaml``; the code only
fills placeholders. :func:`indonesian_forms` is a deterministic check that the
Malay output is Malaysian Malay rather than Indonesian, using the word list in
``locales/ms.yaml``.
"""

from __future__ import annotations

import re
from datetime import date
from functools import cache
from importlib import resources
from typing import Any

import yaml

from ...core.errors import ConfigError

LANGUAGES = ("en", "ms")


@cache
def locale(lang: str) -> dict[str, Any]:
    """The parsed locale file for ``lang`` (``en`` or ``ms``)."""
    if lang not in LANGUAGES:
        raise ConfigError(f"language must be one of {', '.join(LANGUAGES)}, not '{lang}'")
    text = (
        resources.files("crewforge.recipes.academic")
        .joinpath("locales", f"{lang}.yaml")
        .read_text(encoding="utf-8")
    )
    return yaml.safe_load(text)


def t(lang: str, key: str, **values: Any) -> str:
    """Look up ``section.key`` in the locale and fill its placeholders."""
    node: Any = locale(lang)
    for part in key.split("."):
        node = node[part]
    return str(node).format(**values) if values else str(node)


def llm_instruction(lang: str) -> str:
    return t(lang, "llm_instruction")


def style_name(lang: str, style: str) -> str:
    return locale(lang)["styles"].get(style, style.upper())


def format_date(lang: str, day: date) -> str:
    return f"{day.day} {locale(lang)['months'][day.month - 1]} {day.year}"


@cache
def _indonesian_patterns() -> list[tuple[re.Pattern[str], str]]:
    data = locale("ms")
    patterns = [
        (re.compile(rf"(?<!\w){re.escape(word)}(?!\w)", re.IGNORECASE), malay)
        for word, malay in (data.get("indonesian_forms") or {}).items()
    ]
    for suffix, malay_suffix in (data.get("indonesian_suffixes") or {}).items():
        suffix_re = re.compile(rf"(?<!\w)(\w{{3,}}){re.escape(suffix)}(?!\w)", re.IGNORECASE)
        patterns.append((suffix_re, malay_suffix))
    return patterns


def indonesian_forms(text: str) -> dict[str, str]:
    """Indonesian forms found in ``text``, mapped to the Malaysian form to use.

    A warning signal, not a verdict: proper names (e.g. *Universitas Terbuka*)
    legitimately keep their Indonesian spelling.
    """
    found: dict[str, str] = {}
    for pattern, malay in _indonesian_patterns():
        for match in pattern.finditer(text):
            word = match.group(0)
            if pattern.groups:  # suffix rule: keep the stem, swap the ending
                malay_word = match.group(1) + malay
            else:
                malay_word = malay
            found.setdefault(word.lower(), malay_word.lower())
    return found
