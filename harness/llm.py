"""DeepSeek chat completions over the OpenAI-compatible HTTP API.

Thinking mode is set explicitly on every request. The provider's assistant
message is returned verbatim, ``reasoning_content`` included; callers append it
unchanged, which passes all earlier reasoning back as DeepSeek requires for
every request that carries ``tools`` (missing reasoning is an HTTP 400). The
same verbatim history keeps each prompt an exact extension of the previous
prompt plus output, which is what DeepSeek's prefix cache can reuse.
"""

from __future__ import annotations

import os
import random
import re
import time
from dataclasses import dataclass

import httpx

ASSISTANT_FIELDS = ("role", "content", "reasoning_content", "tool_calls")
RETRYABLE = {429, 500, 502, 503, 504}
FATAL = {401, 402, 403}  # key, balance or permission: stop the whole batch
CONTEXT_LIMIT = re.compile(r"context length|maximum context|too many tokens", re.IGNORECASE)


@dataclass(frozen=True)
class ModelConfig:
    model: str
    base_url: str = "https://api.deepseek.com"
    api_key_env: str = "DEEPSEEK_API_KEY"
    thinking: str = "enabled"  # "enabled" | "disabled"
    reasoning_effort: str | None = "high"
    max_tokens: int = 32768
    temperature: float | None = None  # sent only with thinking disabled
    timeout: float = 900.0
    retries: int = 3  # transport failures, 429 and 5xx only


class ProviderError(RuntimeError):
    """The provider rejected or never answered: rerun the task, never score it.

    ``context_length`` is the exception: the request itself exceeded the model's
    context, which a rerun cannot fix; runners record it as an incomplete run.
    """

    def __init__(self, kind: str, message: str, status: int | None = None):
        super().__init__(f"{kind}: {message}")
        self.kind = kind
        self.status = status

    @property
    def fatal(self) -> bool:
        return self.status in FATAL


@dataclass
class Completion:
    message: dict
    finish_reason: str | None
    usage: dict
    latency: float
    response_id: str | None
    raw_usage: dict | None = None
    served_model: str | None = None
    fingerprint: str | None = None


def normalize_usage(raw: dict | None) -> dict:
    raw = raw or {}
    prompt = int(raw.get("prompt_tokens") or 0)
    hit = raw.get("prompt_cache_hit_tokens")
    if hit is None:  # OpenAI-style field, should DeepSeek's own be absent
        hit = (raw.get("prompt_tokens_details") or {}).get("cached_tokens")
    hit = int(hit or 0)
    miss = raw.get("prompt_cache_miss_tokens")
    details = raw.get("completion_tokens_details") or {}
    return {
        "prompt_tokens": prompt,
        "completion_tokens": int(raw.get("completion_tokens") or 0),
        "cache_hit_tokens": hit,
        "cache_miss_tokens": int(miss) if miss is not None else prompt - hit,
        "reasoning_tokens": int(details.get("reasoning_tokens") or 0),
    }


def check_reasoning_passback(messages: list[dict]) -> None:
    """Raise where DeepSeek would answer 400: an earlier assistant turn without reasoning."""
    for index, message in enumerate(messages):
        if message.get("role") == "assistant" and "reasoning_content" not in message:
            raise ValueError(f"Assistant message {index} lacks reasoning_content")


class ChatClient:
    """Thread-safe client for one model configuration."""

    def __init__(self, cfg: ModelConfig, transport: httpx.BaseTransport | None = None):
        self.cfg = cfg
        key = os.environ.get(cfg.api_key_env, "")
        if not key and transport is None:
            raise RuntimeError(f"{cfg.api_key_env} is not set")
        self._http = httpx.Client(
            base_url=cfg.base_url,
            timeout=cfg.timeout,
            headers={"Authorization": f"Bearer {key}"},
            transport=transport,
        )

    def request_body(self, messages, tools=None, tool_choice=None, effort=None) -> dict:
        cfg = self.cfg
        body = {
            "model": cfg.model,
            "messages": messages,
            "max_tokens": cfg.max_tokens,
            "thinking": {"type": cfg.thinking},
        }
        if cfg.thinking == "enabled":
            if effort or cfg.reasoning_effort:
                body["reasoning_effort"] = effort or cfg.reasoning_effort
        elif cfg.temperature is not None:
            body["temperature"] = cfg.temperature
        if tools:
            body["tools"] = tools
            if tool_choice:
                body["tool_choice"] = tool_choice
        return body

    def complete(self, messages, tools=None, tool_choice=None, effort=None) -> Completion:
        """``effort`` overrides the configured reasoning effort for this request only."""
        if tools and self.cfg.thinking == "enabled":
            check_reasoning_passback(messages)
        start = time.monotonic()
        data = self._post(self.request_body(messages, tools, tool_choice, effort))
        latency = time.monotonic() - start
        try:
            choice = data["choices"][0]
            raw = choice["message"]
        except (KeyError, IndexError, TypeError) as error:
            raise ProviderError("malformed_response", repr(error)) from error
        finish = choice.get("finish_reason")
        if finish == "insufficient_system_resource":
            raise ProviderError(finish, "Provider interrupted the generation")
        message = {key: raw[key] for key in ASSISTANT_FIELDS if key in raw}
        message["role"] = "assistant"
        if self.cfg.thinking == "enabled":
            message.setdefault("reasoning_content", "")
        return Completion(
            message,
            finish,
            normalize_usage(data.get("usage")),
            latency,
            data.get("id"),
            raw_usage=data.get("usage"),
            served_model=data.get("model"),
            fingerprint=data.get("system_fingerprint"),
        )

    def _post(self, body: dict) -> dict:
        for attempt in range(self.cfg.retries + 1):
            try:
                response = self._http.post("/chat/completions", json=body)
            except httpx.TransportError as error:
                failure = ProviderError("transport", repr(error))
            else:
                if response.status_code == 200:
                    try:
                        return response.json()
                    except ValueError as error:
                        raise ProviderError("malformed_response", repr(error)) from error
                status, text = response.status_code, response.text[:2000]
                if status == 400 and CONTEXT_LIMIT.search(text):
                    raise ProviderError("context_length", text, status)
                failure = ProviderError(f"http_{status}", text, status)
                if status not in RETRYABLE:
                    raise failure
            if attempt == self.cfg.retries:
                raise failure
            time.sleep(min(60.0, 5.0 * 2**attempt) * (0.5 + random.random()))
        raise AssertionError("unreachable")
