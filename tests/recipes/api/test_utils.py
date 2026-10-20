"""Tests for utility functions."""

import pytest

from crewforge.recipes.api.utils import (
    chunk_list,
    deep_merge,
    estimate_tokens,
    extract_json_from_text,
    flatten_dict,
    format_duration,
    hash_content,
    load_json_file,
    safe_filename,
    save_json_file,
    slugify,
    truncate,
)


class TestSlugify:
    def test_basic(self):
        assert slugify("Hello World") == "hello-world"

    def test_special_chars(self):
        assert slugify("API v2.0!") == "api-v2-0"

    def test_multiple_spaces(self):
        assert slugify("a  b  c") == "a-b-c"


class TestTruncate:
    def test_short(self):
        assert truncate("hi", 10) == "hi"

    def test_long(self):
        assert truncate("hello world", 8) == "hello..."

    def test_custom_suffix(self):
        assert truncate("hello", 4, "~") == "hel~"


class TestHashContent:
    def test_consistent(self):
        assert hash_content("test") == hash_content("test")

    def test_length(self):
        assert len(hash_content("anything")) == 16


class TestSafeFilename:
    def test_basic(self):
        assert safe_filename("My File!") == "my-file"

    def test_spaces(self):
        assert safe_filename("a b c") == "a-b-c"


class TestChunkList:
    def test_even(self):
        assert chunk_list([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]

    def test_odd(self):
        assert chunk_list([1, 2, 3], 2) == [[1, 2], [3]]


class TestDeepMerge:
    def test_flat(self):
        assert deep_merge({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}

    def test_override(self):
        assert deep_merge({"a": 1}, {"a": 2}) == {"a": 2}

    def test_nested(self):
        assert deep_merge({"a": {"x": 1}}, {"a": {"y": 2}}) == {"a": {"x": 1, "y": 2}}


class TestFlattenDict:
    def test_flat(self):
        assert flatten_dict({"a": 1}) == {"a": 1}

    def test_nested(self):
        assert flatten_dict({"a": {"b": 1}}) == {"a.b": 1}


class TestEstimateTokens:
    def test_basic(self):
        assert estimate_tokens("hello") >= 1

    def test_long(self):
        assert estimate_tokens("a" * 100) > 10


class TestFormatDuration:
    def test_ms(self):
        assert "ms" in format_duration(0.5)

    def test_seconds(self):
        assert "s" in format_duration(5.0)

    def test_minutes(self):
        assert "m" in format_duration(120)


class TestExtractJson:
    def test_plain_json(self):
        assert extract_json_from_text('{"a": 1}') == {"a": 1}

    def test_code_block(self):
        assert extract_json_from_text('```json\n{"a": 1}\n```') == {"a": 1}

    def test_no_json(self):
        assert extract_json_from_text("no json here") is None


class TestFileIO:
    def test_save_load(self, tmp_path):
        p = tmp_path / "test.json"
        save_json_file(p, {"key": "value"})
        data = load_json_file(p)
        assert data["key"] == "value"

    def test_load_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_json_file(tmp_path / "missing.json")
