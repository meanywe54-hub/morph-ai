import json

from morph.agents import ModelAgent
from morph.core import Task


class Model:
    def __init__(self, reply):
        self.reply = reply
        self.prompts = []
        self.last_usage = {"input_tokens": 10, "output_tokens": 3, "cost_usd": 0.002}

    def complete(self, prompt):
        self.prompts.append(prompt)
        return self.reply


def test_model_agent_hides_reference_and_records_usage():
    model = Model(json.dumps({"answer": 4}))
    run = ModelAgent(model).run(Task("example", "math", "validation", (3, 1), 987654))
    assert run.answer == 4
    assert run.model_calls == 1
    assert run.cost_usd == 0.002
    assert "987654" not in model.prompts[0]
    assert "[3, 1]" in model.prompts[0]


def test_model_agent_records_invalid_output_as_failure():
    run = ModelAgent(Model('{"answer": true}')).run(Task("x", "math", "development", (2,), 2))
    assert run.answer is None
    assert run.error is not None
    assert run.model_calls == 1
