"""The api crew: parse a description, then build spec, routes, models, auth, tests and docs.

Deterministic agents (schema, test_gen, validator) never call the LLM. The LLM
agents return code only through a fenced block that must compile, and the
parser must return the documented JSON shape with at least one endpoint;
anything else fails the run naming the agent (apiforge used to fall back to
an empty description that a later agent filled with invented routes).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...core.agent import Agent
from ...core.client import LLMClient
from ...core.errors import OutputParseError
from ...core.parsing import extract_code_block
from ...core.usage import UsageTracker

HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")


@dataclass
class ParsedEndpoint:
    path: str
    method: str
    description: str
    parameters: list[dict[str, Any]] = field(default_factory=list)
    request_body: dict[str, Any] | None = None
    response_schema: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    auth_required: bool = True


@dataclass
class APIDescription:
    title: str
    description: str
    version: str = "1.0.0"
    base_path: str = "/api/v1"
    endpoints: list[ParsedEndpoint] = field(default_factory=list)
    auth_type: str = "bearer"
    models: list[dict[str, Any]] = field(default_factory=list)


class ApiAgent(Agent):
    """Base for the api agents (keeps apiforge's ``run(**kwargs)`` entry point)."""

    def __init__(
        self, client: LLMClient | None = None, tracker: UsageTracker | None = None, **kwargs: Any
    ) -> None:
        super().__init__(client, tracker, **kwargs)  # type: ignore[arg-type]

    async def run(self, **kwargs: Any) -> Any:  # pragma: no cover - abstract
        raise NotImplementedError

    def code_from(self, content: str) -> str:
        """The fenced Python block of a reply; it must exist and compile."""
        code = extract_code_block(content, "python")
        if code is None or not code.strip():
            raise OutputParseError(self.name, "no ```python code block in the reply", content[:120])
        try:
            compile(code, f"<{self.name}>", "exec")
        except SyntaxError as exc:
            raise OutputParseError(
                self.name, f"generated code does not compile: {exc.msg} (line {exc.lineno})"
            ) from exc
        return code.strip() + "\n"

    async def review_code(self, code: str, instructions: str) -> str:
        response = await self.ask(
            f"{instructions}\nReturn the complete file in ONE ```python code block.\n"
            f"```python\n{code}\n```"
        )
        return self.code_from(response.content)


# ------------------------------------------------------------------------- parser

_SCHEMA_HINT = """Reply with ONE JSON object and nothing else (no prose, no markdown).
Use exactly this shape:
{
  "title": "string",
  "description": "string",
  "version": "1.0.0",
  "base_path": "/api/v1",
  "auth_type": "bearer" | "api_key" | "none",
  "endpoints": [
    {
      "path": "/resource/{id}",
      "method": "GET" | "POST" | "PUT" | "PATCH" | "DELETE",
      "description": "string",
      "parameters": [
        {"name": "id", "in": "path" | "query",
         "type": "string" | "integer" | "boolean", "required": true}
      ],
      "request_body": {"field": "type"} | null,
      "response_schema": {"field": "type"},
      "tags": ["string"],
      "auth_required": true
    }
  ],
  "models": [
    {"name": "Resource", "fields": [{"name": "id", "type": "string", "required": true}]}
  ]
}
Paths are relative to base_path. Include every endpoint the user describes."""


class ParserAgent(ApiAgent):
    name = "parser"
    description = "Turns a natural-language API description into a structured spec"
    system_prompt = (
        "You are the parser of an API scaffolding crew. Turn a natural-language API "
        "description into a structured JSON spec.\n" + _SCHEMA_HINT
    )
    temperature = 0.0

    def to_description(self, data: dict[str, Any]) -> APIDescription:
        endpoints: list[ParsedEndpoint] = []
        for i, ep in enumerate(data.get("endpoints") or []):
            if not isinstance(ep, dict) or not ep.get("path"):
                raise OutputParseError(self.name, f"endpoint #{i + 1} has no path")
            method = str(ep.get("method", "GET")).upper()
            if method not in HTTP_METHODS:
                raise OutputParseError(self.name, f"endpoint {ep['path']} has method {method!r}")
            path = "/" + str(ep["path"]).lstrip("/")
            endpoints.append(
                ParsedEndpoint(
                    path=path,
                    method=method,
                    description=str(ep.get("description") or f"{method} {path}"),
                    parameters=list(ep.get("parameters") or []),
                    request_body=ep.get("request_body") or None,
                    response_schema=ep.get("response_schema") or {},
                    tags=list(ep.get("tags") or []),
                    auth_required=bool(ep.get("auth_required", True)),
                )
            )
        if not endpoints:
            raise OutputParseError(self.name, "the spec has no endpoints")
        return APIDescription(
            title=str(data.get("title") or "API"),
            description=str(data.get("description") or ""),
            version=str(data.get("version") or "1.0.0"),
            base_path="/" + str(data.get("base_path") or "/api/v1").strip("/"),
            endpoints=endpoints,
            auth_type=str(data.get("auth_type") or "bearer"),
            models=[m for m in data.get("models") or [] if isinstance(m, dict) and m.get("name")],
        )

    async def parse(self, description: str) -> APIDescription:
        data = await self.ask_json(
            "Parse this API description into the JSON shape above:\n" + description
        )
        return self.to_description(data)

    async def run(self, **kwargs: Any) -> APIDescription:
        return await self.parse(kwargs["description"])


# --------------------------------------------------------------- deterministic


def _func_name(method: str, path: str) -> str:
    stem = path.strip("/").replace("/", "_").replace("{", "").replace("}", "").replace("-", "_")
    return f"{method.lower()}_{stem or 'root'}"


class SchemaAgent(ApiAgent):
    """Builds the OpenAPI 3.1 document from the parsed description (no LLM call)."""

    name = "schema"
    description = "Builds the OpenAPI 3.1 spec (deterministic)"

    def _build_paths(self, desc: APIDescription) -> dict[str, Any]:
        paths: dict[str, Any] = {}
        for ep in desc.endpoints:
            op: dict[str, Any] = {
                "summary": ep.description,
                "operationId": _func_name(ep.method, ep.path),
                "tags": ep.tags or ["default"],
                "responses": {
                    "200": {
                        "description": "Success",
                        "content": {
                            "application/json": {"schema": ep.response_schema or {"type": "object"}}
                        },
                    }
                },
            }
            if ep.parameters:
                op["parameters"] = [
                    {
                        "name": p.get("name"),
                        "in": p.get("in", "query"),
                        "required": p.get("required", p.get("in") == "path"),
                        "schema": {"type": p.get("type", "string")},
                    }
                    for p in ep.parameters
                ]
            if ep.request_body and ep.method in ("POST", "PUT", "PATCH"):
                op["requestBody"] = {
                    "required": True,
                    "content": {"application/json": {"schema": ep.request_body}},
                }
            if ep.auth_required and desc.auth_type != "none":
                op["security"] = [{"bearerAuth": []}]
            paths.setdefault(ep.path, {})[ep.method.lower()] = op
        return paths

    def _build_schemas(self, desc: APIDescription) -> dict[str, Any]:
        schemas: dict[str, Any] = {}
        for m in desc.models:
            props, req = {}, []
            for f in m.get("fields", []):
                props[f["name"]] = {"type": f.get("type", "string")}
                if f.get("required"):
                    req.append(f["name"])
            schemas[m["name"]] = {"type": "object", "properties": props, "required": req}
        return schemas

    async def generate_spec(self, desc: APIDescription) -> dict[str, Any]:
        return {
            "openapi": "3.1.0",
            "info": {"title": desc.title, "description": desc.description, "version": desc.version},
            "servers": [{"url": desc.base_path}],
            "paths": self._build_paths(desc),
            "components": {
                "schemas": self._build_schemas(desc),
                "securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}},
            },
            "security": [{"bearerAuth": []}],
        }

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        return await self.generate_spec(kwargs["description"])


class TestAgent(ApiAgent):
    """Writes a pytest smoke test per endpoint (no LLM call)."""

    __test__ = False  # not a pytest test class despite the name
    name = "test_gen"
    description = "Writes pytest smoke tests for every endpoint (deterministic)"

    @staticmethod
    def _sample_path(desc: APIDescription, path: str) -> str:
        full = desc.base_path.rstrip("/") + path
        for part in [s for s in full.split("/") if s.startswith("{")]:
            full = full.replace(part, "1")
        return full

    async def generate_tests(self, desc: APIDescription) -> str:
        lines = ['"""Auto-generated smoke tests (crewforge)."""', ""]
        for ep in desc.endpoints:
            method = ep.method.lower()
            url = self._sample_path(desc, ep.path)
            lines.append(f"def test_{_func_name(ep.method, ep.path)}(client):")
            lines.append(
                f'    """{ep.method} {ep.path} answers (auth or validation errors allowed)."""'
            )
            if ep.method == "GET" or ep.method == "DELETE":
                lines.append(f'    resp = client.{method}("{url}")')
            else:
                lines.append(f'    resp = client.{method}("{url}", json={{}})')
            lines.append("    assert resp.status_code in (200, 201, 204, 401, 403, 422)")
            lines.append("")
        return "\n".join(lines)

    async def run(self, **kwargs: Any) -> str:
        return await self.generate_tests(kwargs["description"])


# --------------------------------------------------------------------- LLM code


class RouterAgent(ApiAgent):
    name = "router"
    description = "Writes the FastAPI routes"
    system_prompt = (
        "You write FastAPI route modules. Keep every route path, HTTP method and the "
        "module-level `router` variable exactly as given; improve the bodies, typing and "
        "docstrings only."
    )

    def _generate_code(self, desc: APIDescription) -> str:
        lines = [
            '"""Auto-generated FastAPI routes (crewforge)."""',
            "from fastapi import APIRouter, Query",
            "",
            f'router = APIRouter(prefix="{desc.base_path}")',
            "",
        ]
        for ep in desc.endpoints:
            method = ep.method.lower()
            params = []
            for p in ep.parameters:
                ptype = {"integer": "int", "string": "str", "boolean": "bool"}.get(
                    p.get("type", "string"), "str"
                )
                if p.get("in") == "path":
                    params.append(f"{p['name']}: {ptype}")
                else:
                    params.append(f"{p['name']}: {ptype} | None = Query(None)")
            if ep.request_body and method in ("post", "put", "patch"):
                params.append("body: dict")
            lines.append(f'@router.{method}("{ep.path}")')
            lines.append(f"async def {_func_name(ep.method, ep.path)}({', '.join(params)}):")
            lines.append(f'    """{ep.description}"""')
            lines.append("    return {}")
            lines.append("")
        return "\n".join(lines)

    async def generate_routes(self, desc: APIDescription) -> str:
        return await self.review_code(
            self._generate_code(desc), "Review and improve this FastAPI routes module."
        )

    async def run(self, **kwargs: Any) -> str:
        return await self.generate_routes(kwargs["description"])


class ModelAgent(ApiAgent):
    name = "model"
    description = "Writes the Pydantic v2 models"
    system_prompt = "You write Pydantic v2 models. Keep every class and field name as given."
    TYPE_MAP = {"string": "str", "integer": "int", "boolean": "bool", "number": "float"}

    @classmethod
    def _generate_models(cls, desc: APIDescription) -> str:
        lines = ['"""Auto-generated models (crewforge)."""', "from pydantic import BaseModel", ""]
        for m in desc.models:
            lines.append(f"class {m['name']}(BaseModel):")
            fields = m.get("fields") or []
            for fld in fields:
                ftype = cls.TYPE_MAP.get(fld.get("type", "string"), "str")
                if not fld.get("required", True):
                    lines.append(f"    {fld['name']}: {ftype} | None = None")
                else:
                    lines.append(f"    {fld['name']}: {ftype}")
            if not fields:
                lines.append("    pass")
            lines.append("")
        return "\n".join(lines)

    async def generate_models(self, desc: APIDescription) -> str:
        return await self.review_code(self._generate_models(desc), "Review these Pydantic models.")

    async def run(self, **kwargs: Any) -> str:
        return await self.generate_models(kwargs["description"])


_BEARER = '''"""JWT bearer auth."""
import os

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer

sec = HTTPBearer()
SECRET = os.environ["JWT_SECRET"]


async def get_user(creds=Depends(sec)):
    try:
        return jwt.decode(creds.credentials, SECRET, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token") from None
'''

_API_KEY = '''"""API key auth."""
import os

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

header = APIKeyHeader(name="X-API-Key")
KEYS = {k for k in os.getenv("API_KEYS", "").split(",") if k}


async def verify(key: str = Security(header)):
    if key not in KEYS:
        raise HTTPException(403, "Invalid API key")
    return key
'''


class AuthAgent(ApiAgent):
    name = "auth"
    description = "Writes the auth dependency (JWT bearer or API key)"
    system_prompt = "You review FastAPI auth code for security problems and fix them."

    async def generate_auth(self, auth_type: str = "bearer") -> str:
        code = _API_KEY if auth_type == "api_key" else _BEARER
        return await self.review_code(code, "Review this auth code.")

    async def run(self, **kwargs: Any) -> str:
        return await self.generate_auth(kwargs.get("auth_type", "bearer"))


class DocAgent(ApiAgent):
    name = "doc_gen"
    description = "Writes API.md"
    system_prompt = (
        "You write clear API documentation in Markdown. Document only the endpoints you "
        "are given; do not invent any."
    )

    def _skeleton(self, desc: APIDescription) -> str:
        lines = [
            f"# {desc.title}",
            "",
            desc.description,
            "",
            "## Base URL",
            f"`{desc.base_path}`",
            "",
            "## Authentication",
            f"Type: {desc.auth_type}",
            "",
            "## Endpoints",
            "",
        ]
        for ep in desc.endpoints:
            lines.append(f"### `{ep.method} {ep.path}`")
            lines.append(ep.description)
            if ep.parameters:
                lines.append("| Name | In | Type | Required |")
                lines.append("|------|-----|------|----------|")
                for p in ep.parameters:
                    lines.append(
                        f"| {p.get('name')} | {p.get('in', 'query')} | "
                        f"{p.get('type', 'string')} | {p.get('required', False)} |"
                    )
            lines.append("")
        return "\n".join(lines)

    async def generate_docs(self, desc: APIDescription) -> str:
        response = await self.ask("Improve this API documentation:\n\n" + self._skeleton(desc))
        return response.content.strip() + "\n"

    async def run(self, **kwargs: Any) -> str:
        return await self.generate_docs(kwargs["description"])


# ---------------------------------------------------------------------- validate


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str]
    warnings: list[str]
    score: int  # 0-100
    operations: int = 0  # how many operations were actually checked

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "score": self.score,
            "operations_checked": self.operations,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class ValidateAgent:
    """Checks an OpenAPI document offline (no LLM call, no key needed)."""

    name = "validator"
    description = "Checks an OpenAPI spec (deterministic)"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def validate(self, spec: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        if not isinstance(spec, dict):
            return ValidationResult(False, ["Spec is not a JSON object"], [], 0)
        if "openapi" not in spec:
            errors.append("Missing openapi version")
        if "info" not in spec:
            errors.append("Missing info object")
        paths = spec.get("paths")
        if paths is None:
            errors.append("Missing paths object")
        elif not paths:
            errors.append("No endpoints defined (paths is empty)")
        info = spec.get("info") if isinstance(spec.get("info"), dict) else {}
        if not info.get("title"):
            errors.append("Missing API title")
        if not info.get("version"):
            errors.append("Missing API version")
        operations = 0
        for path, methods in (paths or {}).items() if isinstance(paths, dict) else []:
            if not isinstance(methods, dict):
                errors.append(f"Path {path} is not an object")
                continue
            for method, op in methods.items():
                if method not in ("get", "post", "put", "delete", "patch"):
                    continue
                operations += 1
                if not isinstance(op, dict) or "responses" not in op:
                    errors.append(f"Missing responses for {method.upper()} {path}")
                elif "summary" not in op and "operationId" not in op:
                    warnings.append(f"Missing summary for {method.upper()} {path}")
        if paths and operations == 0:
            # A validator that checked nothing must not hand out a score.
            errors.append("No HTTP operations found under paths (validator checked 0 operations)")
        score = 0 if operations == 0 else max(0, 100 - len(errors) * 10 - len(warnings) * 2)
        return ValidationResult(
            valid=not errors, errors=errors, warnings=warnings, score=score, operations=operations
        )

    async def run(self, **kwargs: Any) -> ValidationResult:
        return await self.validate(kwargs["spec"])
