"""Shared fixtures for the api recipe tests (ported from apiforge's conftest)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from crewforge.core.client import LLMClient
from crewforge.core.config import LLMConfig
from crewforge.core.usage import UsageTracker
from tests.recipes.api.fakes import completion


@pytest.fixture
def config() -> LLMConfig:
    return LLMConfig(api_key="test-key", base_url="https://test.api.com/v1")


@pytest.fixture
def tracker() -> UsageTracker:
    return UsageTracker()


@pytest.fixture
def mock_response():
    return completion


@pytest.fixture
def mock_client(mock_response):
    client = AsyncMock(spec=LLMClient)
    client.chat = AsyncMock(return_value=mock_response())
    return client
