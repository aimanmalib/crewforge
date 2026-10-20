"""Structured-output parsing: tolerant of real model formatting, strict about garbage."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from crewforge.core.errors import EmptyOutputError, OutputParseError
from crewforge.core.parsing import extract_code_block, extract_json, parse_json


@pytest.mark.parametrize(
    "text",
    [
        '{"a": 1}',
        '```json\n{"a": 1}\n```',
        '```JSON\n{"a": 1}\n```',
        'Sure! Here is the result:\n```\n{"a": 1}\n```\nLet me know.',
        'Result: {"a": 1} (as requested)',
    ],
)
def test_extract_json_handles_real_model_formatting(text):
    assert extract_json(text) == {"a": 1}


def test_extract_json_arrays_and_nothing():
    assert extract_json("Items: [1, 2, 3]") == [1, 2, 3]
    assert extract_json("no json here") is None
    assert extract_json("") is None
    assert extract_json(None) is None


def test_extract_json_returns_falsy_values_faithfully():
    assert extract_json("{}") == {}
    assert extract_json("[]") == []


def test_parse_json_names_the_agent_on_prose():
    with pytest.raises(OutputParseError) as info:
        parse_json("I think the code looks fine overall.", agent="security")
    assert info.value.agent == "security"
    assert "no JSON found" in str(info.value)
    assert "looks fine" in str(info.value)  # excerpt helps debugging


def test_parse_json_empty_is_empty_output_error():
    with pytest.raises(EmptyOutputError, match="agent 'quality' returned empty output"):
        parse_json("  \n", agent="quality")


def test_parse_json_type_mismatch():
    with pytest.raises(OutputParseError, match="expected a JSON dict, got list"):
        parse_json("[1, 2]", agent="parser")
    assert parse_json("[1]", agent="x", expect=list) == [1]
    assert parse_json('{"a":1}', agent="x", expect=(dict, list)) == {"a": 1}


class Score(BaseModel):
    overall_score: float
    notes: list[str] = []


def test_parse_json_schema_validation():
    model = parse_json('```json\n{"overall_score": 86}\n```', agent="quality", schema=Score)
    assert model.overall_score == 86
    with pytest.raises(OutputParseError, match="does not match Score: overall_score"):
        parse_json('{"score": 86}', agent="quality", schema=Score)


def test_extract_code_block_prefers_language():
    text = "```text\nnot it\n```\n```python\nprint(1)\n```"
    assert extract_code_block(text, "python") == "print(1)"
    assert extract_code_block(text) == "not it"
    assert extract_code_block("plain text") is None
