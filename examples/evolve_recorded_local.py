"""One local synthesis attempt and bounded evaluation against a frozen baseline.

Only development observations are sent to the generator. No arbitrary Python is executed.
"""

import argparse
import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import httpx

from morph.bounded import BoundedRunner
from morph.core import Run, Task
from morph.evolution import PatchedAgent
from morph.experiment import Observation, compare, evaluate
from morph.patches import synthesize
from morph.sandbox import SandboxFailure


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    raw = args.baseline.read_bytes()
    baseline = json.loads(raw)
    if baseline["status"] != "completed":
        raise ValueError("completed baseline required")
    rows = []
    for item in baseline["observations"]:
        run = Run(**item["run"])
        passed = run.error is None and run.answer == item["expected"]
        if (
            type(item["passed"]) is not bool
            or item["passed"] != passed
            or run.task_id != item["task_id"]
        ):
            raise ValueError("inconsistent baseline observation")
        rows.append(
            Observation(
                item["task_id"],
                item["category"],
                item["split"],
                item["expected"],
                run,
                passed,
                tuple(item["values"]),
            )
        )
    if len({x.task_id for x in rows}) != len(rows) or len({x.values for x in rows}) != len(rows):
        raise ValueError("distinct baseline tasks required")
    development = [x for x in rows if x.split == "development"]
    validation = [x for x in rows if x.split == "validation"]
    if not development or not validation:
        raise ValueError("both splits are required")
    schema = {
        "type": "object",
        "properties": {"hypothesis": {"type": "string"}, "code": {"type": "string"}},
        "required": ["hypothesis", "code"],
        "additionalProperties": False,
    }
    runner = BoundedRunner()
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "stage": "generating",
        "baseline_sha256": hashlib.sha256(raw).hexdigest(),
        "baseline_mode": "recorded executions",
        "development_inputs": [list(x.values) for x in development],
        "development_task_ids": [x.task_id for x in development],
        "generator_model": args.model,
        "runtime": runner.runtime,
        "limitations": [
            "Single synthetic candidate; no holdout used",
            "Baseline was recorded in an earlier run",
            "Candidate replaces arithmetic execution; no general agent integration",
            "No acceptance or activation is performed",
        ],
    }
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
    with httpx.Client(trust_env=False, timeout=180) as client:
        inventory = client.get("http://127.0.0.1:11434/api/tags")
        inventory.raise_for_status()
        selected = next(m for m in inventory.json()["models"] if m["name"] == args.model)
        if selected.get("remote_host") or selected.get("remote_model"):
            raise ValueError("installed local model required")
        report["generator_digest"] = selected["digest"]
        report["generator_options"] = {
            "temperature": 0,
            "seed": 0,
            "num_predict": 1024,
            "num_gpu": 0,
            "num_ctx": 4096,
        }

        class Generator:
            def complete(self, prompt):
                request = {
                    "model": args.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "think": False,
                    "format": schema,
                    "options": report["generator_options"],
                }
                report["generator_request"] = request
                response = client.post("http://127.0.0.1:11434/api/chat", json=request)
                response.raise_for_status()
                report["generator_response"] = response.json()
                return report["generator_response"]["message"]["content"]

        try:
            patch = synthesize(
                Generator(),
                development,
                "openai:" + baseline["configuration"]["model"],
                instructions=runner.synthesis_instructions,
                runtime=runner.runtime,
            )
            report["patch"] = asdict(patch)
            runner.validate(patch.code)
            tasks = [Task(x.task_id, x.category, x.split, x.values, x.expected) for x in validation]
            report["comparison"] = compare(validation, evaluate(PatchedAgent(patch, runner), tasks))
            report["stage"] = "validation_complete"
        except (ValueError, SandboxFailure) as exc:
            report["stage"] = "candidate_rejected"
            report["error"] = str(exc)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "stage": report["stage"],
                "comparison": {
                    k: report.get("comparison", {}).get(k)
                    for k in ("baseline_success", "candidate_success", "status")
                },
            }
        )
    )


if __name__ == "__main__":
    main()
