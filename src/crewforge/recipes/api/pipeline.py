"""API scaffolding pipeline: parse → spec → (routes ∥ models ∥ auth ∥ tests ∥ docs) → validate."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from ...core.client import LLMClient
from ...core.config import LLMConfig
from ...core.crew import Crew
from ...core.usage import UsageTracker
from .agents import (
    APIDescription,
    AuthAgent,
    DocAgent,
    ModelAgent,
    ParserAgent,
    RouterAgent,
    SchemaAgent,
    TestAgent,
    ValidateAgent,
    ValidationResult,
)


@dataclass
class PipelineResult:
    description: APIDescription
    openapi_spec: dict[str, Any]
    router_code: str
    model_code: str
    auth_code: str
    test_code: str
    docs: str
    validation: ValidationResult
    token_summary: dict[str, Any] = field(default_factory=dict)
    tracker: UsageTracker | None = field(default=None, repr=False)


class ApiPipeline:
    """Orchestrates the api agents on one crew."""

    def __init__(
        self,
        config: LLMConfig | None = None,
        *,
        client: LLMClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config or LLMConfig()
        self._client = client
        self._transport = transport
        self.validator = ValidateAgent()

    async def generate(self, description: str) -> PipelineResult:
        crew = Crew("scaffold", self.config, client=self._client, transport=self._transport)
        async with crew:
            parser = crew.agent(ParserAgent)
            desc = await crew.step(parser, parser.parse(description))
            spec = await crew.step("schema", crew.agent(SchemaAgent).generate_spec(desc))

            work = {
                "router": crew.agent(RouterAgent).generate_routes(desc),
                "auth": crew.agent(AuthAgent).generate_auth(desc.auth_type),
                "test_gen": crew.agent(TestAgent).generate_tests(desc),
                "doc_gen": crew.agent(DocAgent).generate_docs(desc),
            }
            if desc.models:
                work["model"] = crew.agent(ModelAgent).generate_models(desc)
            out = await crew.parallel(work)
            model_code = out.get("model") or ModelAgent._generate_models(desc)
            validation = await crew.step("validator", self.validator.validate(spec))
        return PipelineResult(
            description=desc,
            openapi_spec=spec,
            router_code=out["router"],
            model_code=model_code,
            auth_code=out["auth"],
            test_code=out["test_gen"],
            docs=out["doc_gen"],
            validation=validation,
            token_summary=crew.tracker.summary(),
            tracker=crew.tracker,
        )
