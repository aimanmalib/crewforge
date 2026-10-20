"""Tests for ProjectScaffold."""

from crewforge.recipes.api.agents import APIDescription, ValidationResult
from crewforge.recipes.api.pipeline import PipelineResult
from crewforge.recipes.api.scaffold import ProjectScaffold


class TestScaffold:
    def _make_result(self):
        return PipelineResult(
            description=APIDescription(title="Test", description="Test API"),
            openapi_spec={
                "openapi": "3.1.0",
                "info": {"title": "T", "version": "1"},
                "paths": {},
            },
            router_code="# routes",
            model_code="# models",
            auth_code="# auth",
            test_code="# tests",
            docs="# docs",
            validation=ValidationResult(valid=True, errors=[], warnings=[], score=100),
        )

    def test_scaffold_creates_files(self, tmp_path):
        s = ProjectScaffold(tmp_path / "out")
        result = self._make_result()
        files = s.scaffold(result)
        assert "routes" in files
        assert "openapi" in files

    def test_scaffold_creates_directory(self, tmp_path):
        out = tmp_path / "new" / "project"
        s = ProjectScaffold(out)
        result = self._make_result()
        s.scaffold(result)
        assert out.exists()

    def test_scaffold_writes_main(self, tmp_path):
        s = ProjectScaffold(tmp_path / "out")
        result = self._make_result()
        files = s.scaffold(result)
        main_path = files["main"]
        assert main_path.exists()
        content = main_path.read_text()
        assert "FastAPI" in content

    def test_scaffold_writes_docs(self, tmp_path):
        s = ProjectScaffold(tmp_path / "out")
        result = self._make_result()
        files = s.scaffold(result)
        assert files["docs"].exists()

    def test_scaffold_writes_requirements(self, tmp_path):
        s = ProjectScaffold(tmp_path / "out")
        result = self._make_result()
        files = s.scaffold(result)
        assert files["requirements"].exists()
        content = files["requirements"].read_text()
        assert "fastapi" in content
