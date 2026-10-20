"""Tests for CodeGenerator."""

from crewforge.recipes.api.generator import CodeGenerator


class TestCodeGenerator:
    def test_render_fastapi_main(self):
        gen = CodeGenerator()
        result = gen.render_fastapi_main("My API", ["routes"])
        assert "My API" in result

    def test_render_test(self):
        gen = CodeGenerator()
        result = gen.render_test("test_get_items", "get", "/items")
        assert "test_get_items" in result

    def test_render_model(self):
        gen = CodeGenerator()
        result = gen.render_model("User", [{"name": "id", "type": "int"}])
        assert "User" in result

    def test_render_route(self):
        gen = CodeGenerator()
        result = gen.render_route("/items", "get", "get_items", [])
        assert "/items" in result

    def test_render_dockerfile(self):
        gen = CodeGenerator()
        result = gen.render("dockerfile.j2", {})
        assert "python" in result.lower()

    def test_render_requirements(self):
        gen = CodeGenerator()
        result = gen.render("requirements.j2", {})
        assert "fastapi" in result

    def test_render_env_example(self):
        gen = CodeGenerator()
        result = gen.render("env.example.j2", {})
        assert "JWT_SECRET" in result
        # The generated API does not call an LLM, so no LLM keys belong here.
        assert "MIMO" not in result

    def test_render_docker_compose(self):
        gen = CodeGenerator()
        result = gen.render("docker-compose.j2", {})
        assert "api" in result
