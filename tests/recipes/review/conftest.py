"""Fixtures for the review recipe (ported from codeguard's tests)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from crewforge.core.client import LLMClient
from crewforge.core.config import LLMConfig
from crewforge.core.usage import UsageTracker


@pytest.fixture
def config() -> LLMConfig:
    return LLMConfig(provider="openai", api_key="test-key")


@pytest.fixture
def agent_setup():
    """(client, tracker) for agents whose ``client.chat`` is replaced in-test."""
    return AsyncMock(spec=LLMClient), UsageTracker()
