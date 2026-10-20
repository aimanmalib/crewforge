"""Tests for ValidateAgent."""

import pytest

from crewforge.recipes.api.agents import ValidateAgent


class TestValidateAgent:
    @pytest.mark.asyncio
    async def test_valid_spec(self, config, mock_client, tracker):
        spec = {
            "openapi": "3.1.0",
            "info": {"title": "T", "version": "1.0"},
            "paths": {
                "/x": {
                    "get": {
                        "summary": "Get X",
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        }
        agent = ValidateAgent(mock_client, tracker)
        r = await agent.validate(spec)
        assert r.valid is True
        assert r.score == 100

    @pytest.mark.asyncio
    async def test_invalid_spec_missing_openapi(self, config, mock_client, tracker):
        agent = ValidateAgent(mock_client, tracker)
        r = await agent.validate({})
        assert r.valid is False
        assert len(r.errors) > 0

    @pytest.mark.asyncio
    async def test_warns_on_missing_summary(self, config, mock_client, tracker):
        spec = {
            "openapi": "3.1.0",
            "info": {"title": "T", "version": "1"},
            "paths": {"/x": {"get": {"responses": {"200": {"description": "ok"}}}}},
        }
        agent = ValidateAgent(mock_client, tracker)
        r = await agent.validate(spec)
        assert len(r.warnings) > 0


class TestValidatorEmptyPaths:
    @pytest.mark.asyncio
    async def test_empty_paths_is_an_error(self, config, mock_client, tracker):
        spec = {"openapi": "3.1.0", "info": {"title": "T", "version": "1"}, "paths": {}}
        agent = ValidateAgent(mock_client, tracker)
        result = await agent.validate(spec)
        assert result.valid is False
        assert any("No endpoints" in e for e in result.errors)
