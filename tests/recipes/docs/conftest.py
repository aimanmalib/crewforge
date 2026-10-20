"""Shared fixtures for the docs recipe tests (ported from documind's conftest)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from crewforge.core.client import LLMClient
from crewforge.core.usage import UsageTracker
from crewforge.recipes.docs import DocsSettings
from tests.recipes.docs.fakes import completion


@pytest.fixture
def config():
    """Docs settings with small chunks (documind's DocuMindConfig chunk settings)."""
    return DocsSettings(chunk_size=256, chunk_overlap=32, retrieval_k=3, citation_format="apa")


@pytest.fixture
def tracker():
    return UsageTracker()


@pytest.fixture
def mock_response():
    """Factory for canned chat responses."""
    return completion


@pytest.fixture
def mock_client(mock_response):
    """Mock LLM client whose ``chat`` returns a canned response."""
    client = AsyncMock(spec=LLMClient)
    client.chat = AsyncMock(return_value=mock_response())
    return client


@pytest.fixture
def sample_text():
    """Sample document text for testing."""
    return """# Test Document

This is a test document for the DocuMind pipeline. It contains multiple paragraphs
and sections to test chunking, indexing, and retrieval.

## Section 1: Introduction

Document analysis is the process of extracting useful information from text documents.
Natural language processing techniques are used to understand the content and structure.

## Section 2: Methods

The pipeline uses multiple agents working together. First, the ingester parses the document.
Then the indexer builds a searchable index. Finally, the retriever finds relevant chunks.

## Section 3: Results

The system achieves high accuracy in question answering tasks. Token usage is tracked
per agent for cost optimization. The MiMo model provides excellent reasoning capabilities.

## Section 4: Conclusion

DocuMind demonstrates effective multi-agent document Q&A. Future work includes
adding more document formats and improving retrieval accuracy.
"""


@pytest.fixture
def sample_doc_path(sample_text, tmp_path):
    """Write sample text to a temporary file."""
    p = tmp_path / "test_document.md"
    p.write_text(sample_text)
    return p


@pytest.fixture
def sample_chunks():
    """Pre-built text chunks for testing."""
    from crewforge.recipes.docs import TextChunk

    return [
        TextChunk(
            chunk_id="doc-abc-chunk-0000",
            document_id="doc-abc",
            text="Document analysis is the process of extracting useful information from text.",
            start_offset=0,
            end_offset=80,
            section="Introduction",
        ),
        TextChunk(
            chunk_id="doc-abc-chunk-0001",
            document_id="doc-abc",
            text="The pipeline uses multiple agents working together for document processing.",
            start_offset=81,
            end_offset=155,
            section="Methods",
        ),
        TextChunk(
            chunk_id="doc-abc-chunk-0002",
            document_id="doc-abc",
            text="The system achieves high accuracy with the MiMo model for reasoning tasks.",
            start_offset=156,
            end_offset=232,
            section="Results",
        ),
    ]
