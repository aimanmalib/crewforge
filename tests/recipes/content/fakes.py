"""Canned replies for the content pipeline (from contentforge's integration tests)."""

from __future__ import annotations

import json

from crewforge.core.client import ChatResponse, Usage


def make_response(content: str, prompt_tokens: int = 500, completion_tokens: int = 300):
    return ChatResponse(
        content=content,
        usage=Usage(
            prompt_tokens, completion_tokens, prompt_tokens + completion_tokens, reported=True
        ),
        model="mimo-v2.5-pro",
        latency_ms=100,
    )


AGENT_RESPONSES = {
    "research": json.dumps(
        {"topic": "AI Healthcare", "key_subtopics": [{"title": "Diagnosis", "key_facts": ["f"]}]}
    ),
    "outline": json.dumps(
        {"title": "AI in Healthcare", "sections": [{"heading": "Intro", "word_allocation": 200}]}
    ),
    "writer": "# AI in Healthcare\n\nA comprehensive guide.",
    "seo": json.dumps({"seo_score": 85, "keyword_analysis": {}}),
    "editor": "# AI in Healthcare (Edited)\n\nPolished guide.",
    "quality": json.dumps({"overall_score": 90, "pass_threshold": True}),
    "translator": "# AI dalam Penjagaan Kesihatan\n\nPanduan.",
    "publisher": json.dumps(
        {
            "formats": {"social_twitter": "New guide!"},
            "metadata": {"title": "AI Healthcare", "description": "A guide", "tags": ["ai"]},
        }
    ),
}


def agent_of(payload: dict) -> str:
    """Which content agent sent this request, from its system prompt."""
    system = payload["messages"][0]["content"]
    for name in (
        "Research",
        "Outline",
        "Writer",
        "SEO",
        "Editor",
        "Quality",
        "Translator",
        "Publisher",
    ):
        if f"You are the {name} Agent" in system:
            return name.lower()
    raise AssertionError(f"unknown agent prompt: {system[:60]}")


def router(overrides: dict[str, object] | None = None):
    overrides = overrides or {}

    def respond(payload):
        name = agent_of(payload)
        return overrides.get(name, AGENT_RESPONSES[name])

    return respond
