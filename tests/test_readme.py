"""The README's providers table must match the presets in code."""

from __future__ import annotations

import re
from pathlib import Path

from crewforge.core.providers import PROVIDERS

README = Path(__file__).resolve().parents[1] / "README.md"


def _provider_rows() -> dict[str, list[str]]:
    rows = {}
    for line in README.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\| `([a-z]+)` \|(.*)\|$", line)
        if m:
            rows[m.group(1)] = [c.strip() for c in m.group(2).split("|")]
    return rows


def test_every_preset_is_documented_and_nothing_else():
    assert set(_provider_rows()) == set(PROVIDERS)


def test_documented_values_match_code():
    for name, (label, url, model, key, auth) in _provider_rows().items():
        p = PROVIDERS[name]
        assert label == p.label
        assert (p.base_url and f"`{p.base_url}`" == url) or (not p.base_url and "--base-url" in url)
        assert (p.default_model and f"`{p.default_model}`" == model) or (
            not p.default_model and "--model" in model
        )
        assert key.startswith(f"`{p.env_key}`")
        assert ("(optional)" in key) == p.keyless
        assert ("api-key" in auth) == (p.auth_style == "api-key")
