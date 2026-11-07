"""One local synthesis attempt and bounded evaluation against a frozen baseline.

Only development observations are sent to the generator. An optional holdout
is evaluated after validation. No arbitrary Python is executed.
"""

import argparse
import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import httpx
from openai import OpenAI

from morph.agents import ModelAgent
from morph.bounded import BoundedRunner
from morph.core import Run, Task
from morph.evolution import PatchedAgent
from morph.experiment import Observation, compare, evaluate
from morph.holdout import evaluate_once, load_tasks
from morph.local_baseline import INTEGER_ANSWER_SCHEMA, ollama_answer_model
from morph.patches import synthesize
from morph.sandbox import SandboxFailure


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--code-only", action="store_true")
    parser.add_argument("--holdout", type=Path)
    parser.add_argument("--ledger", type=Path)
    args = parser.parse_args()
    if bool(args.holdout) != bool(args.ledger):
        parser.error("--holdout and --ledger must be supplied together")
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
    response_fields = ["code"] if args.code_only else ["hypothesis", "code"]
    schema = {
        "type": "object",
        "properties": {field: {"type": "string"} for field in response_fields},
        "required": response_fields,
        "additionalProperties": False,
    }
    runner = BoundedRunner()
    configuration = baseline["configuration"]
    provenance = {
        "development_inputs": [list(x.values) for x in development],
        "development_task_ids": [x.task_id for x in development],
    }
    holdout = None
    if args.holdout:
        if configuration.get("response_schema") != INTEGER_ANSWER_SCHEMA:
            raise ValueError("holdout requires a recorded baseline with the integer answer schema")
        holdout = load_tasks(
            args.holdout,
            {**provenance, "comparison": {"baseline_runs": [asdict(x) for x in validation]}},
        )
        # Fingerprint the exact parsed tasks that will be evaluated.
        provenance["holdout_sha256"] = hashlib.sha256(
            json.dumps([asdict(task) for task in holdout], sort_keys=True).encode()
        ).hexdigest()
    report = {
        **provenance,
        "created_at": datetime.now(UTC).isoformat(),
        "stage": "generating",
        "baseline_sha256": hashlib.sha256(raw).hexdigest(),
        "baseline_mode": "recorded executions",
        "generator_model": args.model,
        "code_only": args.code_only,
        "runtime": runner.runtime,
        "limitations": [
            "Single synthetic candidate",
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
        models = {item["name"]: item for item in inventory.json()["models"]}
        for name in {args.model, configuration["model"]} if holdout else {args.model}:
            item = models.get(name)
            if (
                not item
                or not item.get("digest")
                or item.get("remote_host")
                or item.get("remote_model")
            ):
                raise ValueError(f"installed local model required: {name}")
        if holdout and models[configuration["model"]]["digest"] != configuration["digest"]:
            raise ValueError("holdout baseline model digest differs from the recorded baseline")
        version = client.get("http://127.0.0.1:11434/api/version")
        version.raise_for_status()
        report["ollama_version"] = version.json()["version"]
        if holdout and report["ollama_version"] != configuration["ollama_version"]:
            raise ValueError("holdout Ollama version differs from the recorded baseline")
        selected = models[args.model]
        report["generator_digest"] = selected["digest"]
        report["generator_options"] = {
            "temperature": 0,
            "seed": 0,
            "num_predict": 256 if args.code_only else 1024,
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
                start = perf_counter()
                response = client.post("http://127.0.0.1:11434/api/chat", json=request)
                report["synthesis_elapsed_s"] = perf_counter() - start
                response.raise_for_status()
                report["generator_response"] = response.json()
                return report["generator_response"]["message"]["content"]

        try:
            patch = synthesize(
                Generator(),
                development,
                "openai:" + configuration["model"],
                instructions=(
                    "Task: return the exact sum of all signed integers in values. "
                    + runner.synthesis_instructions
                ),
                runtime=runner.runtime,
                code_only=args.code_only,
            )
            report["patch"] = asdict(patch)
            runner.validate(patch.code)
            tasks = [Task(x.task_id, x.category, x.split, x.values, x.expected) for x in validation]
            report["comparison"] = compare(validation, evaluate(PatchedAgent(patch, runner), tasks))
            report["stage"] = "validation_complete"
        except (ValueError, SandboxFailure) as exc:
            report["stage"] = "candidate_rejected"
            report["error"] = str(exc)
        except httpx.HTTPError as exc:
            report["stage"] = "generator_request_failed"
            report["error"] = type(exc).__name__

        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        if holdout and report.get("comparison", {}).get("status") == "eligible_for_review":
            with OpenAI(
                api_key="ollama-local",
                base_url="http://127.0.0.1:11434/v1/",
                max_retries=0,
                http_client=client,
            ) as api:
                model = ollama_answer_model(
                    api,
                    configuration["model"],
                    configuration["seed"],
                    configuration["max_tokens"],
                    answer_schema=True,
                )
                report["holdout"] = evaluate_once(
                    args.ledger,
                    report["holdout_sha256"],
                    ModelAgent(model),
                    PatchedAgent(patch, runner),
                    holdout,
                    metadata={"patch_id": patch.id, "baseline_sha256": report["baseline_sha256"]},
                )
            report["stage"] = "holdout_complete"
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
