"""Canned replies and a router for the fake endpoint (review recipe)."""

from __future__ import annotations

import json

from crewforge.core.client import ChatResponse, Usage

CLEAN = json.dumps({"summary": "looks fine", "findings": []})
SQLI = json.dumps(
    {
        "summary": "SQL injection on line 4",
        "findings": [
            {
                "severity": "critical",
                "title": "SQL injection",
                "description": "query built with f-string",
                "line": 4,
                "cwe": "CWE-89",
            }
        ],
    }
)
SUMMARY = json.dumps(
    {
        "decision": "REQUEST_CHANGES",
        "quality_score": 40,
        "top_issues": ["SQL injection"],
        "summary": "Fix the injection.",
    }
)


def agent_of(payload: dict) -> str:
    """Which review agent sent this request (from its system prompt)."""
    system = payload["messages"][0]["content"]
    if system.startswith("You are the summary agent"):
        return "summary"
    return system.split("You are the ", 1)[1].split(" reviewer", 1)[0]


def router(overrides: dict[str, object] | None = None):
    """Fake-endpoint responder: per-agent replies, defaulting to valid JSON."""
    overrides = overrides or {}

    def respond(payload):
        name = agent_of(payload)
        if name in overrides:
            return overrides[name]
        if name == "summary":
            return SUMMARY
        return SQLI if name == "security" else CLEAN

    return respond


def make_response(content: str = CLEAN, tokens: int = 500) -> ChatResponse:
    return ChatResponse(
        content=content,
        usage=Usage(tokens // 2, tokens // 2, tokens, reported=True),
        model="test-model",
        latency_ms=100,
    )
