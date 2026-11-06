import json

import pytest

from morph.core import Task
from morph.local_baseline import measure, run_ollama


class Model:
    def complete(self, prompt):
        values = json.loads(prompt.split("Integers: ", 1)[1])
        return json.dumps({"answer": sum(values)})


def test_measure_records_all_tasks_and_real_run_configuration(tmp_path):
    output = tmp_path / "result.json"
    tasks = [
        Task("d", "a", "development", (-3, 2), -1),
        Task("v", "b", "validation", (100, -3), 97),
    ]
    result = measure(Model(), {"model": "test", "digest": "abc", "seed": 7}, output, tasks=tasks)
    assert result["status"] == "completed"
    assert result["splits"]["validation"]["successes"] == 1
    assert result["configuration"]["digest"] == "abc"
    assert len(result["observations"]) == 2
    assert result["splits"]["validation"]["input_tokens"] is None
    assert len(result["completions"]) == 2
    assert json.loads(output.read_text())["status"] == "completed"


def test_measure_refuses_to_overwrite_an_existing_experiment(tmp_path):
    output = tmp_path / "result.json"
    output.write_text("existing")
    with pytest.raises(FileExistsError):
        measure(Model(), {}, output)
    assert output.read_text() == "existing"


def test_local_control_records_schema_model_identity_and_runtime(tmp_path, monkeypatch):
    httpx = pytest.importorskip("httpx")
    pytest.importorskip("openai")
    original_client = httpx.Client

    def handle(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "test-local", "digest": "abc"}]})
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "test"})
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": "test-local", "size_vram": 0}]})
        data = json.loads(request.content)
        assert data["response_format"]["json_schema"]["schema"]["required"] == ["answer"]
        values = json.loads(data["messages"][0]["content"].split("Integers: ", 1)[1])
        return httpx.Response(
            200,
            json={
                "id": "test",
                "object": "chat.completion",
                "created": 0,
                "model": "test-local",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": json.dumps({"answer": sum(values)}),
                        },
                    }
                ],
            },
        )

    class LocalTransportClient(original_client):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(handle))

    monkeypatch.setattr(httpx, "Client", LocalTransportClient)
    report = run_ollama("test-local", tmp_path / "result.json", answer_schema=True)
    assert report["configuration"]["digest"] == "abc"
    assert report["configuration"]["response_schema"]["required"] == ["answer"]
    assert report["splits"]["validation"]["successes"] == 40
    assert report["runtime_models"]["models"][0]["size_vram"] == 0
