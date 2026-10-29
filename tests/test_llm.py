import json

import httpx
import pytest

from harness.llm import ChatClient, ModelConfig, ProviderError

SEARCH = {"type": "function", "function": {"name": "search", "description": "s", "parameters": {"type": "object"}}}
REPLY = {
    "id": "r1",
    "choices": [
        {
            "finish_reason": "tool_calls",
            "message": {
                "role": "assistant",
                "content": "",
                "reasoning_content": "think",
                "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": "search", "arguments": '{"query": "x"}'}}
                ],
            },
        }
    ],
    "usage": {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "prompt_cache_hit_tokens": 4,
        "prompt_cache_miss_tokens": 6,
        "completion_tokens_details": {"reasoning_tokens": 3},
    },
}


def client_with(responses, cfg=None):
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        status, body = responses.pop(0)
        return httpx.Response(status, json=body)

    return ChatClient(cfg or ModelConfig(model="deepseek-flash", retries=2), transport=httpx.MockTransport(handler)), sent


def test_thinking_request_and_verbatim_reasoning():
    client, sent = client_with([(200, REPLY)])
    completion = client.complete([{"role": "user", "content": "hi"}], tools=[SEARCH])
    body = sent[0]
    assert body["thinking"] == {"type": "enabled"}
    assert body["reasoning_effort"] == "high"
    assert "temperature" not in body and body["tools"] == [SEARCH]
    assert completion.message["reasoning_content"] == "think"
    assert completion.message["tool_calls"][0]["id"] == "c1"
    assert completion.usage == {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "cache_hit_tokens": 4,
        "cache_miss_tokens": 6,
        "reasoning_tokens": 3,
    }


def test_missing_reasoning_is_rejected_before_sending():
    client, sent = client_with([])
    history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    with pytest.raises(ValueError, match="reasoning_content"):
        client.complete(history, tools=[SEARCH])
    assert sent == []


def test_bad_request_is_not_retried():
    client, sent = client_with([(400, {"error": {"message": "reasoning_content missing"}})])
    with pytest.raises(ProviderError) as error:
        client.complete([{"role": "user", "content": "hi"}])
    assert error.value.status == 400 and len(sent) == 1


def test_rate_limit_is_retried(monkeypatch):
    monkeypatch.setattr("harness.llm.time.sleep", lambda seconds: None)
    client, sent = client_with([(429, {"error": {}}), (200, REPLY)])
    assert client.complete([{"role": "user", "content": "hi"}]).response_id == "r1"
    assert len(sent) == 2


def test_disabled_thinking_sends_temperature():
    cfg = ModelConfig(model="deepseek-flash", thinking="disabled", temperature=0.0)
    client, sent = client_with([(200, REPLY)], cfg)
    client.complete([{"role": "user", "content": "hi"}])
    assert sent[0]["thinking"] == {"type": "disabled"}
    assert sent[0]["temperature"] == 0.0 and "reasoning_effort" not in sent[0]
