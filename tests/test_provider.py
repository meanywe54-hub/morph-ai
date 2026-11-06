from types import SimpleNamespace

import pytest

from morph.providers import OpenAICompatibleModel


def test_model_reads_chat_completion_text():
    class Completions:
        def create(self, **kwargs):
            assert kwargs["model"] == "example"
            assert kwargs["messages"][0]["content"] == "prompt"
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    assert OpenAICompatibleModel(client, "example").complete("prompt") == "ok"


def test_model_rejects_empty_response():
    class Completions:
        def create(self, **kwargs):
            return SimpleNamespace(choices=[])

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    with pytest.raises(ValueError, match="empty"):
        OpenAICompatibleModel(client, "example").complete("prompt")


def test_model_records_usage_and_only_estimates_cost_with_explicit_rates():
    class Completions:
        def create(self, **kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    model = OpenAICompatibleModel(client, "example", input_per_million=2, output_per_million=4)
    model.complete("prompt")
    assert model.last_usage == {"input_tokens": 100, "output_tokens": 50, "cost_usd": 0.0004}
    model = OpenAICompatibleModel(client, "example")
    model.complete("prompt")
    assert model.last_usage["cost_usd"] is None


def test_model_passes_explicit_sampling_configuration():
    class Completions:
        def create(self, **kwargs):
            assert kwargs["temperature"] == 0
            assert kwargs["seed"] == 7
            assert kwargs["max_tokens"] == 128
            assert kwargs["response_format"] == {"type": "json_object"}
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    model = OpenAICompatibleModel(
        client, "example", temperature=0, seed=7, max_tokens=128, json_mode=True
    )
    assert model.complete("prompt") == "{}"


def test_model_can_require_response_schema():
    schema = {
        "type": "object",
        "properties": {"code": {"type": "string"}},
        "required": ["code"],
        "additionalProperties": False,
    }

    class Completions:
        def create(self, **kwargs):
            assert kwargs["response_format"]["json_schema"]["schema"] == schema
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"code":"pass"}'))]
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    model = OpenAICompatibleModel(client, "example", response_schema=schema)
    assert model.complete("prompt") == '{"code":"pass"}'
