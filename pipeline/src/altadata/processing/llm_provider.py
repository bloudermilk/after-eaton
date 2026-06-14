"""OpenRouter chat-completions client used by the LLM extractor.

Uses ``temperature=0`` and requests JSON-formatted output. Retries on
transient HTTP errors and OpenRouter rate-limit responses.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import httpx
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """Raised when an LLM call cannot be completed."""


class _TransientLLMError(RuntimeError):
    """Internal: signals an LLM error worth retrying."""


@dataclass(frozen=True)
class LLMResponse:
    content: str
    input_tokens: int
    output_tokens: int


_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_REQUEST_TIMEOUT = 90.0
_MAX_RETRIES = 3


class OpenRouterProvider:
    """Calls the OpenRouter chat-completions endpoint."""

    def __init__(
        self,
        model_id: str = "anthropic/claude-haiku-4.5",
        *,
        api_key: str | None = None,
        timeout: float = _REQUEST_TIMEOUT,
    ) -> None:
        self.model_id = model_id
        key = api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise LLMError(
                "OPENROUTER_API_KEY not set; cannot construct OpenRouterProvider"
            )
        self._headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        self._timeout = timeout

    def extract(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        body = {
            "model": self.model_id,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        try:
            return self._call(body)
        except RetryError as exc:
            raise LLMError(
                f"OpenRouter call failed after {_MAX_RETRIES} retries"
            ) from exc

    def _call(self, body: dict[str, object]) -> LLMResponse:
        @retry(
            reraise=False,
            stop=stop_after_attempt(_MAX_RETRIES),
            wait=wait_exponential(multiplier=3, exp_base=4, min=3, max=48),
            retry=retry_if_exception_type((httpx.HTTPError, _TransientLLMError)),
        )
        def _do() -> LLMResponse:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(_OPENROUTER_URL, headers=self._headers, json=body)
            if resp.status_code in (408, 429, 500, 502, 503, 504):
                raise _TransientLLMError(
                    f"transient {resp.status_code}: {resp.text[:200]}"
                )
            resp.raise_for_status()
            payload = resp.json()
            if "error" in payload:
                err = payload["error"]
                msg = (
                    err.get("message", "unknown OpenRouter error")
                    if isinstance(err, dict)
                    else str(err)
                )
                raise LLMError(f"OpenRouter error: {msg}")
            try:
                content = payload["choices"][0]["message"]["content"]
                usage = payload.get("usage") or {}
            except (KeyError, IndexError, TypeError) as exc:
                raise LLMError(
                    f"unexpected OpenRouter response shape: {payload}"
                ) from exc
            return LLMResponse(
                content=str(content),
                input_tokens=int(usage.get("prompt_tokens") or 0),
                output_tokens=int(usage.get("completion_tokens") or 0),
            )

        return _do()
