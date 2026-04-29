"""Tests for the OpenRouter client. No live calls — uses pytest-httpx."""

from __future__ import annotations

import pytest
from pytest_httpx import HTTPXMock

from after_eaton.processing.llm_provider import LLMError, OpenRouterProvider


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip tenacity retry waits in tests."""
    import time

    monkeypatch.setattr(time, "sleep", lambda _s: None)


def test_openrouter_provider_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(LLMError, match="OPENROUTER_API_KEY"):
        OpenRouterProvider()


def test_openrouter_provider_basic_call(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://openrouter.ai/api/v1/chat/completions",
        json={
            "choices": [
                {"message": {"content": '{"structures": [], "reasoning": "ok"}'}}
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20},
        },
    )
    provider = OpenRouterProvider(
        model_id="anthropic/claude-sonnet-4-6", api_key="test-key"
    )
    resp = provider.extract("system", "user")
    assert resp.content == '{"structures": [], "reasoning": "ok"}'
    assert resp.input_tokens == 100
    assert resp.output_tokens == 20

    request = httpx_mock.get_request()
    assert request is not None
    assert request.headers["Authorization"] == "Bearer test-key"
    body = request.read()
    assert b"anthropic/claude-sonnet-4-6" in body
    assert b'"temperature":0' in body
    assert b'"response_format"' in body


def test_openrouter_retries_transient_5xx(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://openrouter.ai/api/v1/chat/completions",
        status_code=503,
    )
    httpx_mock.add_response(
        url="https://openrouter.ai/api/v1/chat/completions",
        json={
            "choices": [{"message": {"content": '{"ok": true}'}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3},
        },
    )
    provider = OpenRouterProvider(api_key="test-key")
    resp = provider.extract("s", "u")
    assert resp.content == '{"ok": true}'
    assert len(httpx_mock.get_requests()) == 2


def test_openrouter_raises_on_persistent_failure(httpx_mock: HTTPXMock) -> None:
    for _ in range(3):
        httpx_mock.add_response(
            url="https://openrouter.ai/api/v1/chat/completions",
            status_code=500,
        )
    provider = OpenRouterProvider(api_key="test-key")
    with pytest.raises(LLMError, match="failed after"):
        provider.extract("s", "u")


def test_openrouter_raises_on_unexpected_shape(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://openrouter.ai/api/v1/chat/completions",
        json={"unexpected": "shape"},
    )
    provider = OpenRouterProvider(api_key="test-key")
    with pytest.raises(LLMError, match="unexpected"):
        provider.extract("s", "u")


def test_openrouter_raises_on_error_field(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://openrouter.ai/api/v1/chat/completions",
        json={"error": {"message": "rate limited", "code": 429}},
    )
    provider = OpenRouterProvider(api_key="test-key")
    with pytest.raises(LLMError, match="rate limited"):
        provider.extract("s", "u")
