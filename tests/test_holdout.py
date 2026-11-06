import json

import pytest

from morph.core import Task
from morph.demo import MockAgent, Patch
from morph.holdout import evaluate_once, load_tasks


def test_holdout_is_reserved_once_even_if_tasks_are_renamed(tmp_path):
    db = tmp_path / "registry.db"
    base = MockAgent()
    candidate = MockAgent(Patch("p", "signed", "signed_sum"))
    tasks = [Task("h1", "arithmetic", "holdout", (5, -2), 3)]
    result = evaluate_once(db, "final-1", base, candidate, tasks)
    assert result["baseline_success"] == 0.0
    assert result["candidate_success"] == 1.0
    assert "status" not in result
    with pytest.raises(ValueError, match="already"):
        evaluate_once(db, "final-1", base, candidate, tasks)
    renamed = [Task("renamed", "arithmetic", "holdout", (5, -2), 3)]
    with pytest.raises(ValueError, match="already"):
        evaluate_once(db, "another-id", base, candidate, renamed)
    relabeled = [Task("another", "different", "holdout", (5, -2), 99)]
    with pytest.raises(ValueError, match="already"):
        evaluate_once(db, "third-id", base, candidate, relabeled)


def test_holdout_rejects_wrong_split_before_reservation(tmp_path):
    db = tmp_path / "registry.db"
    task = Task("v1", "arithmetic", "validation", (1,), 1)
    with pytest.raises(ValueError, match="holdout"):
        evaluate_once(db, "final-1", MockAgent(), MockAgent(), [task])


def test_holdout_loader_rejects_overlap_and_missing_provenance(tmp_path):
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps([{"id": "h", "category": "a", "values": [1, 2], "expected": 3}]))
    report = {
        "development_inputs": [[5, -2]],
        "development_task_ids": ["dev1"],
        "comparison": {"baseline_runs": [{"task_id": "v1", "values": [1, 2]}]},
    }
    with pytest.raises(ValueError, match="overlap"):
        load_tasks(path, report)
    with pytest.raises(ValueError, match="provenance"):
        load_tasks(path, {})


def test_holdout_loader_rejects_id_overlap(tmp_path):
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps([{"id": "v1", "category": "a", "values": [10], "expected": 10}]))
    report = {
        "development_inputs": [[5]],
        "development_task_ids": ["dev1"],
        "comparison": {"baseline_runs": [{"task_id": "v1", "values": [2]}]},
    }
    with pytest.raises(ValueError, match="overlap"):
        load_tasks(path, report)


def test_holdout_rejects_a_reused_input_in_a_new_dataset(tmp_path):
    db = tmp_path / "registry.db"
    first = [Task("a", "x", "holdout", (10, -3), 7)]
    evaluate_once(db, "first", MockAgent(), MockAgent(), first)
    second = [Task("b", "x", "holdout", (10, -3), 7), Task("c", "x", "holdout", (20, -3), 17)]
    with pytest.raises(ValueError, match="already"):
        evaluate_once(db, "second", MockAgent(), MockAgent(), second)
    # The rejected reservation must not consume the new input or dataset ID.
    result = evaluate_once(db, "second", MockAgent(), MockAgent(), [second[1]])
    assert result["n"] == 1
