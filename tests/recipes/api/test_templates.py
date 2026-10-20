"""Tests for Jinja2 templates."""

from crewforge.recipes.api.generator import CodeGenerator


class TestCodeGenerator:
    def test_render_fastapi_main(self):
        gen = CodeGenerator()
        result = gen.render_fastapi_main("Test API", ["routes"])
        assert "Test API" in result

    def test_render_test(self):
        gen = CodeGenerator()
        result = gen.render_test("test_get_items", "get", "/items")
        assert "test_get_items" in result
