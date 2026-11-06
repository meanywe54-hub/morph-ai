"""Exercise the actual optional SDK with an in-process HTTP transport, no network."""

import json

import pytest

openai = pytest.importorskip("openai")
httpx = pytest.importorskip("httpx")

from morph.agents import ModelAgent
from morph.core import Task
from morph.providers import OpenAICompatibleModel


def test_model_agent_uses_openai_sdk_chat_protocol():
    requests = []

    def handle(request):
        requests.append(request)
        body = json.loads(request.content)
        assert body["model"] == "test-model"
        assert "[4, -1]" in body["messages"][0]["content"]
        return httpx.Response(
            200,
            json={
                "id": "test",
                "object": "chat.completion",
                "created": 0,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": '{"answer": 3}'},
                    }
                ],
                "usage": {"prompt_tokens": 11, "completion_tokens": 4, "total_tokens": 15},
            },
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handle))
    with openai.OpenAI(
        api_key="test-only", base_url="http://localhost/v1", http_client=http_client
    ) as client:
        model = OpenAICompatibleModel(
            client, "test-model", input_per_million=1, output_per_million=2
        )
        run = ModelAgent(model).run(Task("id", "math", "validation", (4, -1), 3))
    assert len(requests) == 1
    assert requests[0].url.path == "/v1/chat/completions"
    assert run.answer == 3 and run.model_calls == 1
    assert run.cost_usd == pytest.approx(0.000019)
