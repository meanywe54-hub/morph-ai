"""The real adapter contract with deterministic stand-ins; no network or Docker."""

import json

import pytest

from morph.agents import ModelAgent
from morph.core import Task
from morph.demo import synthesis_tasks
from morph.evolution import PatchedAgent, evolve
from morph.holdout import evaluate_once
from morph.patches import CodePatch
from morph.registry import activate, register_patch
from morph.router import route
from morph.sandbox import SandboxResult


class Model:
    def complete(self, prompt):
        return '{"answer": 0}'


class Synthesizer:
    def complete(self, prompt):
        return json.dumps(
            {"hypothesis": "sum signed values", "code": "def solve(values): return sum(values)"}
        )


class Runner:
    def run(self, code, values):
        return SandboxResult(sum(values))


def test_synthetic_full_lifecycle_requires_review_and_reserves_holdout(tmp_path):
    baseline = ModelAgent(Model())
    runner = Runner()
    development, validation = synthesis_tasks()
    report = evolve(baseline, Synthesizer(), runner, development, validation, "test-model")
    assert report["comparison"]["status"] == "eligible_for_review"
    db = tmp_path / "registry.db"
    patch = report["patch"]
    register_patch(db, patch, report["comparison"]["status"], evidence=report["comparison"])
    assert not route(db, "ledger", report)["use_patch"]
    activate(db, patch["id"], approved_by="test reviewer", reason="test")
    assert route(db, "ledger", report)["use_patch"]
    candidate = PatchedAgent(CodePatch(**patch), runner)
    tasks = [Task("holdout-1", "new", "holdout", (900, -20), 880)]
    final = evaluate_once(db, "final", baseline, candidate, tasks)
    assert final["baseline_success"] == 0
    assert final["candidate_success"] == 1
    with pytest.raises(ValueError, match="already"):
        evaluate_once(db, "final", baseline, candidate, tasks)
