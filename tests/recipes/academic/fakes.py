"""Canned replies and a router for the fake endpoint (academic recipe)."""

from __future__ import annotations

import json

BRIEF = json.dumps(
    {
        "title": "AI in Malaysian secondary schools",
        "course": "EDU3013",
        "word_count": 1500,
        "citation_style": "APA 7th",
        "requirements": ["At least 5 peer-reviewed sources"],
        "rubric": [{"criterion": "Analysis", "weight": "30%"}],
        "keywords": ["AI", "teaching"],
    }
)

PLAN = json.dumps(
    {
        "working_title": "AI and teaching in Malaysian schools",
        "research_questions": ["How do teachers use AI?", "What are the risks?"],
        "outline": [
            {"heading": "Introduction", "purpose": "aim", "key_points": ["context"], "words": 100},
            {"heading": "Uses", "purpose": "evidence", "key_points": ["examples"], "words": 400},
            {"heading": "Risks", "purpose": "analysis", "key_points": ["equity"], "words": 400},
            {"heading": "Conclusion", "purpose": "answer", "key_points": [], "words": 100},
        ],
        "source_needs": [
            {"need": "MOE policy document", "why": "context", "where_to_look": "moe.gov.my"}
        ],
        "search_queries": ['"generative AI" Malaysia secondary school'],
        "suggested_readings": [
            {
                "reference": "Selwyn, N. (2019). Should robots replace teachers? Polity. "
                "ISBN 978-0-306-40615-7",
                "why": "critical overview",
            },
            {
                "reference": "Tan, A. (2022). AI in Malaysian classrooms. Journal of Things.",
                "why": "local",
            },
        ],
    }
)


def feedback_reply(comments=None, summary="Clear overall.") -> str:
    return json.dumps(
        {
            "summary": summary,
            "strengths": ["Good topic"],
            "comments": comments if comments is not None else [],
        }
    )


def agent_of(payload: dict) -> str:
    """Which academic agent sent this request (from its system prompt)."""
    system = payload["messages"][0]["content"]
    if system.startswith("You read assignment briefs"):
        return "brief"
    if system.startswith("You help a student PLAN"):
        return "planner"
    if system.startswith("You format references"):
        return "formatter"
    return system.split("You are the ", 1)[1].split(" reviewer", 1)[0]


def router(overrides: dict[str, object] | None = None):
    overrides = overrides or {}

    def respond(payload):
        name = agent_of(payload)
        if name in overrides:
            value = overrides[name]
            return value(payload) if callable(value) else value
        if name == "brief":
            return BRIEF
        if name == "planner":
            return PLAN
        if name == "formatter":
            return formatter_echo(payload)
        return feedback_reply()

    return respond


def formatter_echo(payload: dict) -> str:
    """Format each numbered input reference by returning it unchanged."""
    prompt = payload["messages"][-1]["content"]
    listing = prompt.split("REFERENCES SUPPLIED BY THE STUDENT:\n", 1)[1].split("\n\nReturn", 1)[0]
    refs = []
    for line in listing.splitlines():
        number, _, text = line.partition(". ")
        refs.append({"index": int(number), "formatted": text, "missing": []})
    return json.dumps({"references": refs})
