import json

import pytest

from morph.demo import MockAgent, tasks
from morph.experiment import evaluate
from morph.patches import synthesize


class RecordingModel:
    def __init__(self, answer):
        self.answer = answer
        self.prompt = ""

    def complete(self, prompt):
        self.prompt = prompt
        return self.answer


def test_synthesis_uses_only_development_evidence():
    dev, _ = tasks()
    model = RecordingModel(
        json.dumps(
            {"hypothesis": "signed input", "code": "def solve(values):\n    return sum(values)"}
        )
    )
    patch = synthesize(model, evaluate(MockAgent(), dev), "agent-v1")
    assert patch.code.startswith("def solve")
    assert patch.source_agent == "agent-v1"
    assert "dev-1" in model.prompt
    assert '"values": [5, -2]' in model.prompt


def test_synthesis_rejects_validation_observations():
    _, validation = tasks()
    with pytest.raises(ValueError, match="development"):
        synthesize(RecordingModel("{}"), evaluate(MockAgent(), validation), "agent-v1")


def test_synthesis_rejects_invalid_python():
    dev, _ = tasks()
    model = RecordingModel(json.dumps({"hypothesis": "h", "code": "def solve(:"}))
    with pytest.raises(ValueError, match="syntax"):
        synthesize(model, evaluate(MockAgent(), dev), "agent-v1")
