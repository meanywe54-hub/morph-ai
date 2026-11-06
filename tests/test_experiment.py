import json
import sqlite3

import pytest

from morph.core import Task
from morph.demo import MockAgent, Patch, run_demo
from morph.experiment import compare, evaluate
from morph.registry import save


def test_demo_records_real_paired_outcomes():
    report = run_demo()
    comparison = report["comparison"]
    assert report["diagnosis"]["failures"] == 2
    assert comparison["baseline_success"] == 0.25
    assert comparison["candidate_success"] == 1.0
    assert comparison["improvements"] == 3
    assert comparison["status"] == "inconclusive"


def test_unknown_operations_are_rejected():
    with pytest.raises(ValueError):
        MockAgent(Patch("x", "x", "execute_python"))


def test_regression_rejects_even_with_many_tasks():
    tasks = [Task(str(i), "arithmetic", "validation", (-1,), 1) for i in range(20)]
    baseline = evaluate(MockAgent(), tasks)
    candidate = evaluate(MockAgent(Patch("x", "x", "signed_sum")), tasks)
    assert compare(baseline, candidate)["status"] == "rejected"


def test_selection_rejects_development_and_mismatched_pairs():
    a = evaluate(MockAgent(), [Task("a", "x", "development", (1,), 1)])
    with pytest.raises(ValueError):
        compare(a, a)
    b = evaluate(MockAgent(), [Task("b", "x", "validation", (1,), 1)])
    with pytest.raises(ValueError):
        compare(a, b)


def test_selection_rejects_same_id_with_different_inputs():
    a = evaluate(MockAgent(), [Task("same", "x", "validation", (1,), 1)])
    b = evaluate(MockAgent(), [Task("same", "x", "validation", (2,), 1)])
    with pytest.raises(ValueError, match="paired"):
        compare(a, b)


def test_candidate_execution_error_cannot_be_eligible():
    from morph.core import Run

    class BrokenAgent:
        def run(self, task):
            if task.id == "0":
                return Run(task.id, -1, 0)
            return Run(task.id, None, 0, error="sandbox failed")

    tasks = [Task(str(i), "x", "validation", (-1,), -1) for i in range(20)]
    assert (
        compare(evaluate(MockAgent(), tasks), evaluate(BrokenAgent(), tasks))["status"]
        == "inconclusive"
    )


def test_repeated_identical_inputs_are_not_independent_evidence():
    tasks = [Task(str(i), "x", "validation", (-1,), -1) for i in range(20)]
    candidate = MockAgent(Patch("p", "h", "signed_sum"))
    assert (
        compare(evaluate(MockAgent(), tasks), evaluate(candidate, tasks))["status"]
        == "inconclusive"
    )


def test_sqlite_persists_report(tmp_path):
    path = tmp_path / "experiments.db"
    report = run_demo()
    assert save(path, report) == 1
    with sqlite3.connect(path) as db:
        stored = json.loads(db.execute("SELECT report FROM experiments").fetchone()[0])
    assert stored == json.loads(json.dumps(report))
