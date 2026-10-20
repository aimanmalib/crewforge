"""Shared fixtures for the content recipe tests (ported from contentforge)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from crewforge.core.client import ChatResponse, LLMClient, Usage
from crewforge.core.usage import UsageTracker
from crewforge.recipes.content import ContentSettings, PipelineConfig


@pytest.fixture
def pipeline_config() -> PipelineConfig:
    return PipelineConfig(
        topic="Test Topic",
        target_word_count=1000,
        language="en",
        seo_enabled=True,
        quality_threshold=0.8,
        max_iterations=2,
        enable_translation=False,
        target_languages=["zh"],
    )


@pytest.fixture
def config(pipeline_config, tmp_path) -> ContentSettings:
    return ContentSettings(pipeline=pipeline_config, output_dir=str(tmp_path / "out"))


@pytest.fixture
def tracker() -> UsageTracker:
    return UsageTracker()


@pytest.fixture
def mock_response() -> ChatResponse:
    return ChatResponse(
        content='{"test": "response"}',
        usage=Usage(500, 300, 800, 100, reported=True),
        model="mimo-v2.5-pro",
        finish_reason="stop",
        latency_ms=150.0,
    )


@pytest.fixture
def mock_client(mock_response) -> AsyncMock:
    client = AsyncMock(spec=LLMClient)
    client.chat = AsyncMock(return_value=mock_response)
    return client
