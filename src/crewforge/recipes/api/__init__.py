"""``api`` recipe (from apiforge): natural language -> FastAPI project + OpenAPI spec.

The parser, router, model, auth and docs agents call the LLM; the schema,
test and validator agents are deterministic.
"""

from .agents import (
    APIDescription,
    AuthAgent,
    DocAgent,
    ModelAgent,
    ParsedEndpoint,
    ParserAgent,
    RouterAgent,
    SchemaAgent,
    TestAgent,
    ValidateAgent,
    ValidationResult,
)
from .pipeline import ApiPipeline, PipelineResult
from .scaffold import ProjectScaffold

__all__ = [
    "APIDescription",
    "ApiPipeline",
    "AuthAgent",
    "DocAgent",
    "ModelAgent",
    "ParsedEndpoint",
    "ParserAgent",
    "PipelineResult",
    "ProjectScaffold",
    "RouterAgent",
    "SchemaAgent",
    "TestAgent",
    "ValidateAgent",
    "ValidationResult",
]
