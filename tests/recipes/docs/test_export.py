"""Tests for ExportAgent."""

from __future__ import annotations

import json

import pytest

from crewforge.recipes.docs import Answer, ExportAgent


class TestExportAgent:
    """Test the ExportAgent."""

    @pytest.fixture
    def answers(self):
        return [
            Answer(
                "What is MiMo?",
                "MiMo is great.",
                [
                    {
                        "source_num": "1",
                        "chunk_id": "c1",
                        "document_id": "d1",
                        "excerpt": "test",
                    }
                ],
                "high",
            ),
            Answer("How does it work?", "Very well.", [], "medium"),
        ]

    @pytest.mark.asyncio
    async def test_export_markdown(self, config, mock_client, tracker, answers, tmp_path):
        agent = ExportAgent()
        path = await agent.export_session(answers, tmp_path / "output.md", format="markdown")
        assert path.exists()
        content = path.read_text()
        assert "# crewforge Q&A session" in content

    @pytest.mark.asyncio
    async def test_export_json(self, config, mock_client, tracker, answers, tmp_path):
        agent = ExportAgent()
        path = await agent.export_session(answers, tmp_path / "output.json", format="json")
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["total_questions"] == 2

    @pytest.mark.asyncio
    async def test_export_creates_parent_dirs(
        self, config, mock_client, tracker, answers, tmp_path
    ):
        agent = ExportAgent()
        path = await agent.export_session(answers, tmp_path / "deep" / "dir" / "output.md")
        assert path.exists()

    @pytest.mark.asyncio
    async def test_run_method(self, config, mock_client, tracker, answers, tmp_path):
        agent = ExportAgent()
        path = await agent.run(answers=answers, output_path=str(tmp_path / "run.md"))
        assert path.exists()
