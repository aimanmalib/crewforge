"""Router / model / auth / docs agents (ported from apiforge test_router, test_model,
test_auth and test_doc_agent).

apiforge silently fell back to its template when the model replied without a
code block; crewforge treats that as the agent's failure, so the "no code"
tests now assert the failure names the agent.
"""

from __future__ import annotations

import pytest

from crewforge.core.errors import EmptyOutputError, OutputParseError
from crewforge.recipes.api.agents import (
    APIDescription,
    AuthAgent,
    DocAgent,
    ModelAgent,
    ParsedEndpoint,
    RouterAgent,
)
from tests.recipes.api.fakes import py

ITEMS = APIDescription(
    title="T",
    description="D",
    endpoints=[ParsedEndpoint(path="/items", method="GET", description="List")],
)


class TestRouterAgent:
    @pytest.mark.asyncio
    async def test_generate_routes(self, mock_client, tracker):
        mock_client.chat.return_value.content = "no code blocks"
        with pytest.raises(OutputParseError) as info:
            await RouterAgent(mock_client, tracker).generate_routes(ITEMS)
        assert info.value.agent == "router"

    @pytest.mark.asyncio
    async def test_generates_with_params(self, mock_client, tracker):
        desc = APIDescription(
            title="T",
            description="D",
            endpoints=[
                ParsedEndpoint(
                    path="/items/{id}",
                    method="GET",
                    description="Get item",
                    parameters=[{"name": "id", "in": "path", "type": "integer", "required": True}],
                )
            ],
        )
        agent = RouterAgent(mock_client, tracker)
        skeleton = agent._generate_code(desc)
        assert "def get_items_id(id: int)" in skeleton
        mock_client.chat.return_value.content = py(skeleton)
        code = await agent.generate_routes(desc)
        assert "def " in code and '"/items/{id}"' in code

    @pytest.mark.asyncio
    async def test_non_compiling_code_fails_naming_router(self, mock_client, tracker):
        mock_client.chat.return_value.content = py("def broken(:\n    pass")
        with pytest.raises(OutputParseError, match="does not compile"):
            await RouterAgent(mock_client, tracker).generate_routes(ITEMS)


class TestModelAgent:
    @pytest.mark.asyncio
    async def test_generate_models(self, mock_client, tracker):
        desc = APIDescription(
            title="T",
            description="D",
            models=[{"name": "Item", "fields": [{"name": "title", "type": "string"}]}],
        )
        agent = ModelAgent(mock_client, tracker)
        mock_client.chat.return_value.content = py(agent._generate_models(desc))
        code = await agent.generate_models(desc)
        assert "class Item" in code
        mock_client.chat.return_value.content = "no code"
        with pytest.raises(OutputParseError):
            await agent.generate_models(desc)


class TestAuthAgent:
    @pytest.mark.asyncio
    async def test_generate_bearer(self, mock_client, tracker):
        mock_client.chat.return_value.content = py("import jwt\nSECRET = 'x'\n")
        code = await AuthAgent(mock_client, tracker).generate_auth("bearer")
        assert "jwt" in code
        sent = mock_client.chat.await_args.args[0][-1].content
        assert "HTTPBearer" in sent and 'os.environ["JWT_SECRET"]' in sent

    @pytest.mark.asyncio
    async def test_generate_apikey(self, mock_client, tracker):
        mock_client.chat.return_value.content = "no code"
        with pytest.raises(OutputParseError) as info:
            await AuthAgent(mock_client, tracker).generate_auth("api_key")
        assert info.value.agent == "auth"
        assert "APIKeyHeader" in mock_client.chat.await_args.args[0][-1].content


class TestDocAgent:
    @pytest.mark.asyncio
    async def test_generate_docs(self, mock_client, tracker):
        desc = APIDescription(
            title="Test",
            description="A test API",
            endpoints=[ParsedEndpoint(path="/items", method="GET", description="List items")],
        )
        mock_client.chat.return_value.content = "# Test API"
        docs = await DocAgent(mock_client, tracker).generate_docs(desc)
        assert docs.startswith("# Test API")
        sent = mock_client.chat.await_args.args[0][-1].content
        assert "### `GET /items`" in sent  # the full skeleton is sent, not the first 50 lines

    @pytest.mark.asyncio
    async def test_generate_docs_fallback(self, mock_client, tracker):
        # apiforge silently fell back to the skeleton on an empty reply.
        mock_client.chat.return_value.content = ""
        with pytest.raises(EmptyOutputError) as info:
            await DocAgent(mock_client, tracker).generate_docs(ITEMS)
        assert info.value.agent == "doc_gen"


class TestGeneratedSmokeTests:
    @pytest.mark.asyncio
    async def test_routes_with_ids_accept_not_found(self, mock_client, tracker):
        # Found in a real run: the router kept an in-memory store, so DELETE
        # /todos/1 answered 404 and the generated smoke test failed.
        from crewforge.recipes.api.agents import TestAgent

        desc = APIDescription(
            title="T",
            description="D",
            endpoints=[
                ParsedEndpoint(path="/todos", method="GET", description="List"),
                ParsedEndpoint(path="/todos/{id}", method="DELETE", description="Delete"),
            ],
        )
        code = await TestAgent(mock_client, tracker).generate_tests(desc)
        list_test, delete_test = code.split("def test_")[1:]
        assert "404" not in list_test
        assert "404" in delete_test and '"/api/v1/todos/1"' in delete_test
