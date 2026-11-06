import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from morph.core import Task
from morph.demo import MockAgent, Patch
from morph.experiment import compare, evaluate


def test_cli_register_activate_route_and_rollback(tmp_path):
    patch = Patch("p", "sign", "signed_sum")
    tasks = [Task(str(i), "arithmetic", "validation", (-i - 1, 1), -i) for i in range(20)]
    comparison = compare(evaluate(MockAgent(), tasks), evaluate(MockAgent(patch), tasks))
    report = {"patch": {"id": "p", "operation": "signed_sum"}, "comparison": comparison}
    report_path, db = tmp_path / "report.json", tmp_path / "registry.db"
    report_path.write_text(json.dumps(report), encoding="utf-8-sig")

    def call(*args):
        command = [sys.executable, "-m", "morph.cli", *map(str, args)]
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            cwd=Path(__file__).parents[1],
            env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
        )
        return json.loads(result.stdout)

    call("register", "--db", db, "--report", report_path)
    duplicate = subprocess.run(
        [
            sys.executable,
            "-m",
            "morph.cli",
            "register",
            "--db",
            str(db),
            "--report",
            str(report_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=Path(__file__).parents[1],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
    )
    assert duplicate.returncode != 0
    assert "Traceback" not in duplicate.stderr
    call("activate", "--db", db, "--patch", "p", "--reviewer", "person", "--reason", "reviewed")
    assert call("route", "--db", db, "--report", report_path, "--category", "arithmetic")[
        "use_patch"
    ]
    call("rollback", "--db", db, "--reviewer", "person", "--reason", "disable")
    assert not call("route", "--db", db, "--report", report_path, "--category", "arithmetic")[
        "use_patch"
    ]


@pytest.mark.parametrize("kind", ["operation", "bounded"])
def test_cli_holdout_uses_approved_patch_once(tmp_path, kind):
    patch = Patch("p", "sign", "signed_sum")
    validation = [Task(str(i), "arithmetic", "validation", (-i - 1, 1), -i) for i in range(20)]
    candidate = MockAgent(patch)
    payload = asdict(patch)
    if kind == "bounded":
        from morph.bounded import BoundedRunner
        from morph.evolution import PatchedAgent
        from morph.patches import CodePatch

        code_patch = CodePatch(
            "p",
            "mock-absolute-sum-v1",
            "sign",
            "def solve(values): return sum(values)",
            runtime="bounded-integer-v1",
        )
        candidate = PatchedAgent(code_patch, BoundedRunner())
        payload = asdict(code_patch)
    comparison = compare(evaluate(MockAgent(), validation), evaluate(candidate, validation))
    report = {
        "patch": payload,
        "comparison": comparison,
        "development_inputs": [[5, -2]],
        "development_task_ids": ["dev-1"],
    }
    report_path, task_path, db = (
        tmp_path / "report.json",
        tmp_path / "holdout.json",
        tmp_path / "db.sqlite",
    )
    report_path.write_text(json.dumps(report), encoding="utf-8")
    task_path.write_text(
        json.dumps([{"id": "h1", "category": "arithmetic", "values": [100, -3], "expected": 97}]),
        encoding="utf-8",
    )
    from morph.registry import activate, register_patch

    register_patch(
        db, report["patch"], comparison["status"], evidence=comparison, provenance=report
    )
    activate(db, "p", approved_by="reviewer", reason="reviewed")
    command = [
        sys.executable,
        "-m",
        "morph.cli",
        "holdout",
        "--db",
        str(db),
        "--report",
        str(report_path),
        "--tasks",
        str(task_path),
        "--dataset-id",
        "final-1",
    ]
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")}
    changed_report = {**report, "development_inputs": []}
    report_path.write_text(json.dumps(changed_report), encoding="utf-8")
    rejected = subprocess.run(command, capture_output=True, text=True, check=False, env=env)
    assert rejected.returncode != 0
    assert "report" in rejected.stderr
    report_path.write_text(json.dumps(report), encoding="utf-8")
    result = subprocess.run(command, capture_output=True, text=True, check=True, env=env)
    assert json.loads(result.stdout)["candidate_success"] == 1.0
    repeated = subprocess.run(command, capture_output=True, text=True, check=False, env=env)
    assert repeated.returncode != 0
    assert "already" in repeated.stderr
