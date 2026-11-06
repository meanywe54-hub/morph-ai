"""A single-use evaluation record, separate from candidate selection."""

import hashlib
import json
import sqlite3
from pathlib import Path

from morph.core import AgentAdapter, Task
from morph.experiment import evaluate


def load_tasks(path: Path, report: dict) -> list[Task]:
    """Load structured holdout data and reject exact input overlap with recorded splits."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, list) or not 1 <= len(payload) <= 1000:
            raise ValueError("holdout must contain 1 to 1000 tasks")
        recorded = report["development_inputs"]
        validation = report["comparison"]["baseline_runs"]
        forbidden = {tuple(x) for x in recorded} | {tuple(x["values"]) for x in validation}
        forbidden_ids = set(report["development_task_ids"]) | {x["task_id"] for x in validation}
        tasks = []
        for item in payload:
            values = item["values"]
            if (
                not isinstance(item["id"], str)
                or not item["id"].strip()
                or not isinstance(item["category"], str)
                or not item["category"].strip()
                or not isinstance(values, list)
                or len(values) > 1000
                or any(type(v) is not int or abs(v) > 10**9 for v in values)
                or type(item["expected"]) is not int
            ):
                raise ValueError("invalid holdout task")
            if tuple(values) in forbidden or item["id"] in forbidden_ids:
                raise ValueError("holdout tasks overlap with earlier splits")
            tasks.append(
                Task(item["id"], item["category"], "holdout", tuple(values), item["expected"])
            )
        if len({t.values for t in tasks}) != len(tasks):
            raise ValueError("duplicate holdout inputs")
        return tasks
    except (KeyError, TypeError) as exc:
        raise ValueError("invalid holdout data or missing provenance") from exc


def evaluate_once(
    db_path: Path,
    dataset_id: str,
    baseline: AgentAdapter,
    candidate: AgentAdapter,
    tasks: list[Task],
    *,
    metadata: dict | None = None,
) -> dict:
    """Reserve a holdout before evaluation; even an interrupted run consumes it.

    The registry cannot prevent access outside this API or detect task paraphrases.
    """
    if not dataset_id.strip() or not tasks or any(t.split != "holdout" for t in tasks):
        raise ValueError("a nonempty holdout dataset and ID are required")
    if metadata is not None:
        json.dumps(metadata, allow_nan=False)
    if len({t.id for t in tasks}) != len(tasks):
        raise ValueError("holdout task IDs must be unique")
    contents = sorted(t.values for t in tasks)
    if len(set(contents)) != len(contents):
        raise ValueError("holdout inputs must be unique")
    fingerprint = hashlib.sha256(json.dumps(contents).encode()).hexdigest()
    with sqlite3.connect(db_path) as db:
        old_table = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='holdout_runs'"
        ).fetchone()
        inputs_table = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='holdout_inputs'"
        ).fetchone()
        if (
            old_table
            and not inputs_table
            and db.execute("SELECT 1 FROM holdout_runs LIMIT 1").fetchone()
        ):
            raise ValueError("legacy holdout ledger cannot verify prior input use")
        db.execute(
            "CREATE TABLE IF NOT EXISTS holdout_runs (dataset_id TEXT PRIMARY KEY, "
            "fingerprint TEXT UNIQUE NOT NULL, report TEXT)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS holdout_inputs (digest TEXT PRIMARY KEY, "
            "dataset_id TEXT NOT NULL)"
        )
        try:
            db.execute(
                "INSERT INTO holdout_runs (dataset_id, fingerprint) VALUES (?, ?)",
                (dataset_id, fingerprint),
            )
            db.executemany(
                "INSERT INTO holdout_inputs (digest, dataset_id) VALUES (?, ?)",
                [
                    (hashlib.sha256(json.dumps(values).encode()).hexdigest(), dataset_id)
                    for values in contents
                ],
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("holdout dataset already used") from exc
    a, b = evaluate(baseline, tasks), evaluate(candidate, tasks)
    n = len(tasks)
    report = {
        "dataset_id": dataset_id,
        "n": n,
        "baseline_success": sum(x.passed for x in a) / n,
        "candidate_success": sum(x.passed for x in b) / n,
        "improvements": sum(not x.passed and y.passed for x, y in zip(a, b, strict=True)),
        "regressions": sum(x.passed and not y.passed for x, y in zip(a, b, strict=True)),
        "baseline_errors": sum(x.run.error is not None for x in a),
        "candidate_errors": sum(x.run.error is not None for x in b),
        "baseline_model_calls": sum(x.run.model_calls for x in a),
        "candidate_model_calls": sum(x.run.model_calls for x in b),
        "baseline_cost_usd": (
            sum(x.run.cost_usd for x in a) if all(x.run.cost_usd is not None for x in a) else None
        ),
        "candidate_cost_usd": (
            sum(x.run.cost_usd for x in b) if all(x.run.cost_usd is not None for x in b) else None
        ),
        "baseline_elapsed_s": sum(x.run.elapsed_s for x in a),
        "candidate_elapsed_s": sum(x.run.elapsed_s for x in b),
        "metadata": metadata,
    }
    with sqlite3.connect(db_path) as db:
        db.execute(
            "UPDATE holdout_runs SET report = ? WHERE dataset_id = ?",
            (json.dumps(report, sort_keys=True), dataset_id),
        )
    return report
