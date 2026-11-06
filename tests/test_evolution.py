import json

import pytest

from morph.core import Task
from morph.demo import MockAgent, synthesis_tasks, tasks
from morph.evolution import evolve
from morph.sandbox import SandboxResult


class Model:
    def complete(self, prompt):
        assert "val-1" not in prompt
        return json.dumps({"hypothesis": "signs", "code": "def solve(values): return sum(values)"})


class Runner:
    def run(self, code, values):
        assert "def solve" in code
        return SandboxResult(sum(values))


def test_evolve_connects_development_to_paired_validation():
    development, validation = tasks()
    result = evolve(MockAgent(), Model(), Runner(), development, validation, "mock-v1")
    assert result["comparison"]["candidate_success"] == 1.0
    assert result["comparison"]["status"] == "inconclusive"
    assert result["patch"]["status"] == "candidate"


def test_evolve_rejects_overlapping_task_ids():
    development, _ = tasks()
    with pytest.raises(ValueError, match="unique"):
        evolve(MockAgent(), Model(), Runner(), development, development, "mock-v1")


def test_synthesis_dataset_has_distinct_validation_inputs_and_control_cases():
    development, validation = synthesis_tasks()
    assert len({task.values for task in development + validation}) == len(development + validation)
    assert len(validation) >= 40
    assert any(all(value >= 0 for value in task.values) for task in validation)
    assert any(any(value < 0 for value in task.values) for task in validation)


def test_evolve_rejects_input_overlap_across_splits():
    development, _ = tasks()
    validation = [Task("different-id", "other", "validation", development[0].values, 3)]
    with pytest.raises(ValueError, match="overlap"):
        evolve(MockAgent(), Model(), Runner(), development, validation, "mock-v1")


def test_synthesis_usage_is_captured_before_validation_overwrites_it():
    class SharedModel(Model):
        last_usage = None

        def complete(self, prompt):
            self.last_usage = {"input_tokens": 100, "output_tokens": 20, "cost_usd": 0.1}
            return super().complete(prompt)

    model = SharedModel()

    class Agent(MockAgent):
        def run(self, task):
            model.last_usage = {"input_tokens": 1, "output_tokens": 1, "cost_usd": 0.01}
            return super().run(task)

    development, validation = tasks()
    result = evolve(Agent(), model, Runner(), development, validation, "agent-v1")
    assert result["synthesis_usage"]["input_tokens"] == 100


def test_bounded_evolution_executes_generated_algorithm_without_docker():
    from morph.bounded import BoundedRunner

    class Generator:
        def complete(self, prompt):
            assert "bounded integer" in prompt
            return json.dumps(
                {
                    "hypothesis": "retain signs",
                    "code": "def solve(values):\n total = 0\n for value in values:\n  total += value\n return total",
                }
            )

    development, validation = synthesis_tasks()
    report = evolve(MockAgent(), Generator(), BoundedRunner(), development, validation, "mock-v1")
    assert report["patch"]["runtime"] == "bounded-integer-v1"
    assert report["comparison"]["candidate_success"] == 1
    assert report["comparison"]["status"] == "eligible_for_review"


def test_patch_runtime_cannot_be_switched_after_evaluation():
    from morph.bounded import BoundedRunner
    from morph.evolution import PatchedAgent
    from morph.patches import CodePatch

    patch = CodePatch("p", "source", "hypothesis", "def solve(values): return 1")
    with pytest.raises(ValueError, match="runtime"):
        PatchedAgent(patch, BoundedRunner())
