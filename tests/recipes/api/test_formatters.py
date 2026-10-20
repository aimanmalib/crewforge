"""Tests for formatters."""

from crewforge.recipes.api.formatters import OutputFormatter


class TestFormatters:
    def test_to_json(self):
        r = OutputFormatter.to_json({"a": 1})
        assert '"a": 1' in r

    def test_to_json_compact(self):
        r = OutputFormatter.to_json({"a": 1}, pretty=False)
        assert r == '{"a": 1}'

    def test_markdown_table(self):
        r = OutputFormatter.to_markdown_table(["Name", "Type"], [["id", "int"]])
        assert "Name" in r
        assert "---" in r
        assert "id" in r

    def test_wrap_code(self):
        r = OutputFormatter.wrap_code("print('hi')", "python")
        assert "```python" in r
        assert "print" in r

    def test_file_tree(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("x")
        files = {"test": f}
        r = OutputFormatter.file_tree(files, tmp_path)
        assert "test.py" in r

    def test_markdown_table_empty(self):
        r = OutputFormatter.to_markdown_table(["A", "B"], [])
        assert "A" in r
        assert "B" in r
