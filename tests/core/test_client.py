"""The client's wire format and retry policy, against a fake HTTP endpoint."""

from __future__ import annotations

import json

import httpx
import pytest

from crewforge.core.client import LLMClient, Message, is_retryable_status
from crewforge.core.config import LLMConfig
from crewforge.core.errors import LLMError, LLMHTTPError, LLMResponseError


def make_client(handler, **cfg):
    sleeps: list[float] = []

    async def sleep(seconds):
        sleeps.append(seconds)

    config = LLMConfig(provider="openai", api_key="sk-secret", **cfg)
    client = LLMClient(config, transport=httpx.MockTransport(handler), sleep=sleep)
    return client, sleeps


def ok(content="hi", usage=True, **extra):
    body = {"model": "m", "choices": [{"message": {"content": content}, "finish_reason": "stop"}]}
    if usage:
        body["usage"] = {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}
    body.update(extra)
    return httpx.Response(200, json=body)


async def test_payload_is_non_streaming_and_keeps_zero_temperature():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers.get("authorization")
        seen["url"] = str(request.url)
        return ok()

    client, _ = make_client(handler)
    resp = await client.chat([Message("user", "x")], temperature=0.0, max_tokens=5)
    assert resp.content == "hi"
    assert seen["body"]["stream"] is False
    assert seen["body"]["temperature"] == 0.0
    assert seen["body"]["max_tokens"] == 5
    assert seen["auth"] == "Bearer sk-secret"
    assert seen["url"] == "https://api.openai.com/v1/chat/completions"


async def test_extra_params_cannot_turn_streaming_back_on():
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return ok()

    client, _ = make_client(handler)
    await client.chat([{"role": "user", "content": "x"}], extra={"stream": True, "seed": 1})
    assert seen["stream"] is False and seen["seed"] == 1


async def test_usage_is_taken_from_provider():
    client, _ = make_client(lambda r: ok())
    resp = await client.chat([Message("user", "x")])
    assert (resp.usage.prompt_tokens, resp.usage.completion_tokens) == (7, 3)
    assert resp.usage.total_tokens == 10 and resp.usage.reported
    assert client.total_usage.total_tokens == 10 and client.request_count == 1


async def test_missing_usage_is_marked_unreported_not_invented():
    client, _ = make_client(lambda r: ok(usage=False))
    resp = await client.chat([Message("user", "x")])
    assert resp.usage.reported is False
    assert resp.usage.total_tokens == 0


async def test_null_fields_are_tolerated():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": None}, "finish_reason": None}],
                "usage": {"total_tokens": None, "prompt_tokens_details": None},
            },
        )

    client, _ = make_client(handler)
    resp = await client.chat([Message("user", "x")])
    assert resp.content == "" and resp.finish_reason == ""
    assert resp.usage.total_tokens == 0 and resp.usage.cached_tokens == 0


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
async def test_transient_statuses_are_retried_then_succeed(status):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(status) if len(calls) < 3 else ok("done")

    client, sleeps = make_client(handler, max_retries=3, retry_delay=0.5)
    resp = await client.chat([Message("user", "x")])
    assert resp.content == "done" and resp.attempts == 3
    assert len(calls) == 3
    assert sleeps == [0.5, 1.0]  # exponential backoff


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
async def test_client_errors_are_not_retried(status):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(status, json={"error": {"message": "nope"}})

    client, sleeps = make_client(handler, max_retries=5)
    with pytest.raises(LLMHTTPError) as info:
        await client.chat([Message("user", "x")])
    assert info.value.status_code == status
    assert len(calls) == 1 and sleeps == []
    assert "nope" in str(info.value)


async def test_auth_error_names_env_var_and_never_the_key():
    client, _ = make_client(lambda r: httpx.Response(401, json={"error": "bad key sk-secret"}))
    with pytest.raises(LLMHTTPError) as info:
        await client.chat([Message("user", "x")])
    message = str(info.value)
    assert "OPENAI_API_KEY" in message
    # The provider echoed the key back; we still only quote its message, not our headers.
    assert "Bearer" not in message


async def test_retries_are_bounded():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503)

    client, sleeps = make_client(handler, max_retries=3, retry_delay=1, max_retry_delay=1.5)
    with pytest.raises(LLMHTTPError) as info:
        await client.chat([Message("user", "x")])
    assert len(calls) == 3 and info.value.attempts == 3
    assert sleeps == [1, 1.5]  # capped by max_retry_delay
    assert "after 3 attempts" in str(info.value)


async def test_retry_after_header_is_honoured_but_capped():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "7"})
        return ok()

    client, sleeps = make_client(handler, retry_delay=0.1, max_retry_delay=5)
    await client.chat([Message("user", "x")])
    assert sleeps == [5]


async def test_network_errors_are_retried_then_reported():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    client, sleeps = make_client(handler, max_retries=2, retry_delay=0)
    with pytest.raises(LLMError, match="cannot reach .* after 2 attempt"):
        await client.chat([Message("user", "x")])
    assert len(sleeps) == 1


async def test_timeouts_are_retried():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("slow", request=request)
        return ok("late")

    client, _ = make_client(handler, retry_delay=0)
    assert (await client.chat([Message("user", "x")])).content == "late"


async def test_streamed_body_is_reported_as_response_error():
    client, _ = make_client(lambda r: httpx.Response(200, text='data: {"x":1}\n\ndata: [DONE]\n'))
    with pytest.raises(LLMResponseError, match="non-JSON"):
        await client.chat([Message("user", "x")])


async def test_body_without_choices_is_a_response_error():
    client, _ = make_client(lambda r: httpx.Response(200, json={"error": "overloaded"}))
    with pytest.raises(LLMResponseError, match="no choices"):
        await client.chat([Message("user", "x")])


async def test_reasoning_content_is_kept_separately():
    def handler(request):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "A", "reasoning_content": "because"}}]},
        )

    client, _ = make_client(handler)
    resp = await client.chat([Message("user", "x")])
    assert (resp.content, resp.reasoning) == ("A", "because")


async def test_context_manager_closes_http_client():
    client, _ = make_client(lambda r: ok())
    async with client:
        await client.chat([Message("user", "x")])
    assert client._http is not None and client._http.is_closed


def test_retryable_status_table():
    assert [s for s in (200, 400, 401, 403, 404, 408, 429, 500, 503) if is_retryable_status(s)] == [
        429,
        500,
        503,
    ]
