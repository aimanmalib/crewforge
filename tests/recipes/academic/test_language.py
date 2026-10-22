"""Locales (English + Malaysian Malay) and the Indonesian-forms check."""

from __future__ import annotations

from datetime import date

import pytest

from crewforge.core.errors import ConfigError
from crewforge.recipes.academic.language import (
    format_date,
    indonesian_forms,
    llm_instruction,
    locale,
    style_name,
    t,
)


def _keys(node, prefix=""):
    if isinstance(node, dict):
        out = set()
        for k, v in node.items():
            out |= _keys(v, f"{prefix}{k}.")
        return out
    return {prefix.rstrip(".")}


def test_both_locales_have_the_same_keys():
    en = _keys(locale("en"))
    ms = {k for k in _keys(locale("ms")) if not k.startswith("indonesian_")}
    assert en == ms


def test_placeholders_match_between_locales():
    import re

    for key in _keys(locale("en")):
        node_en, node_ms = locale("en"), locale("ms")
        for part in key.split("."):
            node_en, node_ms = node_en[part], node_ms[part]
        if isinstance(node_en, str):
            assert set(re.findall(r"\{(\w+)\}", node_en)) == set(
                re.findall(r"\{(\w+)\}", node_ms)
            ), key


def test_unknown_language_is_a_config_error():
    with pytest.raises(ConfigError, match="en, ms"):
        locale("id")


def test_lookup_and_formatting():
    assert t("en", "labels.budget_total", total="1,500") == "Total: 1,500 words"
    assert t("ms", "labels.budget_total", total="1,500") == "Jumlah: 1,500 perkataan"
    assert style_name("ms", "apa") == "APA edisi ke-7"
    assert format_date("ms", date(2026, 8, 3)) == "3 Ogos 2026"
    assert format_date("en", date(2026, 8, 3)) == "3 August 2026"


def test_malay_instruction_says_not_indonesian():
    text = llm_instruction("ms")
    assert "Malaysian Malay" in text and "NOT" in text and "Indonesian" in text
    assert "Malay" not in llm_instruction("en")


class TestIndonesianForms:
    def test_finds_indonesian_words_and_suffix(self):
        found = indonesian_forms(
            "Karena kualitas pendidikan, dosen di universitas melakukan penelitian."
        )
        assert found["karena"] == "kerana"
        assert found["kualitas"] == "kualiti"
        assert found["universitas"] == "universiti"
        assert found["dosen"] == "pensyarah"
        assert found["penelitian"] == "kajian"

    def test_multiword_and_month(self):
        found = indonesian_forms("Pembelajaran daring sebagai berikut, pada bulan Agustus.")
        assert found == {
            "daring": "dalam talian",
            "sebagai berikut": "seperti berikut",
            "agustus": "ogos",
        }

    def test_malaysian_malay_is_clean(self):
        text = (
            "Kajian ini meneliti kualiti pembelajaran dalam talian di universiti awam kerana "
            "pensyarah memerlukan sokongan. Aktiviti pelajar dinilai seperti berikut "
            "pada bulan Ogos."
        )
        assert indonesian_forms(text) == {}

    def test_word_boundaries(self):
        assert indonesian_forms("saranan dan standard") == {}
