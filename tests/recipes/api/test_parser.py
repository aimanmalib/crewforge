"""ParserAgent (ported from apiforge tests/test_parser.py).

apiforge fell back to an empty "Parsed API" description on unparseable
replies (which later scored 100/100 with no endpoints). crewforge fails
naming the parser instead; those tests now assert that.
"""

from __future__ import annotations

import json

import pytest

from crewforge.core.errors import OutputParseError
from crewforge.recipes.api.agents import APIDescription, ParsedEndpoint, ParserAgent


class TestParserAgent:
    @pytest.mark.asyncio
    async def test_parse_returns_description(self, mock_client, tracker):
        mock_client.chat.return_value.content = json.dumps(
            {
                "title": "Blog API",
                "description": "A blog",
                "endpoints": [{"path": "/posts", "method": "GET", "description": "List posts"}],
                "models": [],
            }
        )
        result = await ParserAgent(mock_client, tracker).parse("A blog API with posts")
        assert isinstance(result, APIDescription)
        assert result.title == "Blog API"

    @pytest.mark.asyncio
    async def test_parse_extracts_endpoints(self, mock_client, tracker):
        mock_client.chat.return_value.content = json.dumps(
            {
                "title": "T",
                "description": "D",
                "endpoints": [
                    {"path": "/users", "method": "GET", "description": "List users"},
                    {"path": "users", "method": "post", "description": "Create user"},
                ],
            }
        )
        result = await ParserAgent(mock_client, tracker).parse("users API")
        assert [(e.method, e.path) for e in result.endpoints] == [
            ("GET", "/users"),
            ("POST", "/users"),
        ]

    @pytest.mark.asyncio
    async def test_parse_handles_invalid_json(self, mock_client, tracker):
        mock_client.chat.return_value.content = "not json"
        with pytest.raises(OutputParseError) as info:
            await ParserAgent(mock_client, tracker).parse("test")
        assert info.value.agent == "parser"

    def test_parsed_endpoint_defaults(self):
        ep = ParsedEndpoint(path="/x", method="GET", description="test")
        assert ep.auth_required is True and ep.parameters == []


class TestParserRobustness:
    @pytest.mark.asyncio
    async def test_prompt_specifies_json_shape(self, mock_client, tracker):
        mock_client.chat.return_value.content = "{}"
        with pytest.raises(OutputParseError, match="no endpoints"):
            await ParserAgent(mock_client, tracker).parse("todo API")
        system = mock_client.chat.await_args.args[0][0].content
        assert '"endpoints"' in system and '"path"' in system and '"method"' in system

    @pytest.mark.asyncio
    async def test_parse_json_wrapped_in_prose(self, mock_client, tracker):
        mock_client.chat.return_value.content = (
            "Sure! Here is the spec:\n"
            + json.dumps({"title": "Todo API", "endpoints": [{"path": "/todos", "method": "get"}]})
            + "\nLet me know if you need more."
        )
        result = await ParserAgent(mock_client, tracker).parse("todo API")
        assert result.title == "Todo API"
        assert [(e.method, e.path) for e in result.endpoints] == [("GET", "/todos")]

    @pytest.mark.asyncio
    async def test_parse_fenced_json(self, mock_client, tracker):
        mock_client.chat.return_value.content = (
            '```json\n{"title": "X", "endpoints": [{"path": "/x"}]}\n```'
        )
        result = await ParserAgent(mock_client, tracker).parse("x")
        assert result.title == "X"

    @pytest.mark.asyncio
    async def test_parse_non_object_json_falls_back(self, mock_client, tracker):
        mock_client.chat.return_value.content = "[1, 2, 3]"
        with pytest.raises(OutputParseError, match="expected a JSON dict"):
            await ParserAgent(mock_client, tracker).parse("x")

    @pytest.mark.asyncio
    async def test_unknown_method_is_rejected(self, mock_client, tracker):
        mock_client.chat.return_value.content = json.dumps(
            {"endpoints": [{"path": "/x", "method": "FETCH"}]}
        )
        with pytest.raises(OutputParseError, match="FETCH"):
            await ParserAgent(mock_client, tracker).parse("x")
