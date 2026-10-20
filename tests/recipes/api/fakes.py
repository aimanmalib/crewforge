"""Canned replies for the api recipe tests."""

from __future__ import annotations

import json

from crewforge.core.client import ChatResponse, Usage


def completion(content="Test", prompt_tokens=100, completion_tokens=50, total_tokens=None, **_):
    """apiforge's ``CompletionResponse(...)`` as a crewforge ``ChatResponse``."""
    total = prompt_tokens + completion_tokens if total_tokens is None else total_tokens
    return ChatResponse(
        content=content, usage=Usage(prompt_tokens, completion_tokens, total, reported=True)
    )


def py(code: str) -> str:
    return f"Here you go:\n```python\n{code}\n```"


TODO_SPEC = json.dumps(
    {
        "title": "Todo API",
        "description": "Todos",
        "base_path": "/api/v1",
        "auth_type": "bearer",
        "endpoints": [
            {"path": "/todos", "method": "GET", "description": "List todos"},
            {
                "path": "/todos",
                "method": "POST",
                "description": "Create a todo",
                "request_body": {"title": "string"},
            },
            {
                "path": "/todos/{id}",
                "method": "DELETE",
                "description": "Delete a todo",
                "parameters": [{"name": "id", "in": "path", "type": "integer", "required": True}],
            },
        ],
        "models": [{"name": "Todo", "fields": [{"name": "title", "type": "string"}]}],
    }
)


def agent_of(payload: dict) -> str:
    system = payload["messages"][0]["content"]
    for key, name in (
        ("parser of an API", "parser"),
        ("FastAPI route modules", "router"),
        ("Pydantic v2 models", "model"),
        ("auth code", "auth"),
        ("API documentation", "doc_gen"),
    ):
        if key in system:
            return name
    raise AssertionError(system[:80])


def echo_code(payload: dict) -> str:
    """Return the code block the agent sent, unchanged (a 'review' that keeps it)."""
    user = payload["messages"][-1]["content"]
    return py(user.split("```python\n", 1)[1].rsplit("```", 1)[0])


def router(overrides: dict[str, object] | None = None):
    overrides = overrides or {}

    def respond(payload):
        name = agent_of(payload)
        if name in overrides:
            return overrides[name]
        if name == "parser":
            return TODO_SPEC
        if name == "doc_gen":
            return "# Todo API\n\nEndpoints: GET/POST /todos, DELETE /todos/{id}."
        return echo_code(payload)

    return respond
