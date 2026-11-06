"""Generate a candidate from development evidence; never execute the generated code."""

import argparse
import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import httpx
from openai import OpenAI

from morph.core import Run
from morph.experiment import Observation
from morph.patches import synthesize
from morph.providers import OpenAICompatibleModel


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    raw_baseline = args.baseline.read_bytes()
    baseline = json.loads(raw_baseline)
    if baseline["status"] != "completed":
        raise ValueError("baseline run must be completed")
    evidence = [
        Observation(
            item["task_id"],
            item["category"],
            item["split"],
            item["expected"],
            Run(**item["run"]),
            item["passed"],
            tuple(item["values"]),
        )
        for item in baseline["observations"]
        if item["split"] == "development"
    ]
    schema = {
        "type": "object",
        "properties": {"hypothesis": {"type": "string"}, "code": {"type": "string"}},
        "required": ["hypothesis", "code"],
        "additionalProperties": False,
    }
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "status": "generating",
        "baseline_sha256": hashlib.sha256(raw_baseline).hexdigest(),
        "generator_model": args.model,
        "development_task_ids": [x.task_id for x in evidence],
        "configuration": {
            "temperature": 0,
            "seed": 0,
            "max_tokens": 2048,
            "response_schema": schema,
        },
        "limitations": [
            "Generated code has not been executed or evaluated",
            "AST syntax validation is not a security review or evidence of effectiveness",
        ],
    }
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
    with httpx.Client(trust_env=False, timeout=120) as transport:
        inventory = transport.get("http://127.0.0.1:11434/api/tags")
        inventory.raise_for_status()
        selected = next(m for m in inventory.json()["models"] if m["name"] == args.model)
        if selected.get("remote_host") or selected.get("remote_model"):
            raise ValueError("local model required")
        report["generator_digest"] = selected["digest"]
        with OpenAI(
            api_key="ollama-local",
            base_url="http://127.0.0.1:11434/v1/",
            max_retries=0,
            http_client=transport,
        ) as client:
            model = OpenAICompatibleModel(
                client,
                args.model,
                temperature=0,
                seed=0,
                max_tokens=2048,
                response_schema=schema,
                input_per_million=0,
                output_per_million=0,
            )

            class Recorder:
                def complete(self, prompt):
                    report["prompt"] = prompt
                    report["response"] = model.complete(prompt)
                    return report["response"]

            try:
                patch = synthesize(
                    Recorder(), evidence, "openai:" + baseline["configuration"]["model"]
                )
                report["patch"] = asdict(patch)
                report["status"] = "pending_isolated_evaluation"
            except ValueError as exc:
                report["status"] = "generation_failed"
                report["error"] = str(exc)
            report["usage"] = model.last_usage
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "status": report["status"]}))


if __name__ == "__main__":
    main()
