"""Auditable local-model measurement without execution of generated code."""

import hashlib
import json
import os
import platform
import tempfile
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from morph.agents import ModelAgent
from morph.core import Task
from morph.demo import synthesis_tasks
from morph.experiment import evaluate
from morph.patches import TextModel


def _write(path: Path, report: dict) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        temporary = stream.name
    os.replace(temporary, path)


def measure(
    model: TextModel, configuration: dict, output: Path, *, tasks: list[Task] | None = None
) -> dict:
    if tasks is None:
        development, validation = synthesis_tasks()
        tasks = development + validation
    if not tasks or any(t.split not in {"development", "validation"} for t in tasks):
        raise ValueError("development or validation tasks required")
    if len({t.id for t in tasks}) != len(tasks) or len({t.values for t in tasks}) != len(tasks):
        raise ValueError("task IDs and inputs must be distinct")
    payload = [asdict(t) for t in tasks]
    source = Path(__file__).parent
    source_hashes = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(source.glob("*.py"))
    }
    report = {
        "status": "running",
        "started_at": datetime.now(UTC).isoformat(),
        "mode": "real local model; synthetic arithmetic baseline only",
        "configuration": configuration,
        "python": platform.python_version(),
        "source_hashes": source_hashes,
        "tasks": payload,
        "dataset_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
        "observations": [],
        "completions": [],
        "splits": {},
        "limitations": [
            "No patch generated or executed",
            "No holdout or transfer result",
            "Local API charges are zero; hardware and energy costs are unpriced",
            "Seed and zero temperature do not guarantee bitwise reproducibility",
        ],
    }
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)

    class Recorder:
        @property
        def last_usage(self):
            return getattr(model, "last_usage", None)

        def complete(self, prompt):
            event = {"prompt": prompt}
            report["completions"].append(event)
            try:
                response = model.complete(prompt)
                event["response"] = response
                return response
            except Exception as exc:
                event["error"] = type(exc).__name__
                raise

    agent = ModelAgent(Recorder())
    for task in tasks:
        observation = evaluate(agent, [task])[0]
        report["observations"].append(asdict(observation))
        _write(output, report)
    for split in sorted({t.split for t in tasks}):
        rows = [x for x in report["observations"] if x["split"] == split]
        report["splits"][split] = {
            "n": len(rows),
            "successes": sum(x["passed"] for x in rows),
            "errors": sum(x["run"]["error"] is not None for x in rows),
            "model_calls": sum(x["run"]["model_calls"] for x in rows),
            "elapsed_s": sum(x["run"]["elapsed_s"] for x in rows),
            "input_tokens": (
                sum(int(x["run"]["metadata"]["input_tokens"]) for x in rows)
                if all("input_tokens" in x["run"]["metadata"] for x in rows)
                else None
            ),
            "output_tokens": (
                sum(int(x["run"]["metadata"]["output_tokens"]) for x in rows)
                if all("output_tokens" in x["run"]["metadata"] for x in rows)
                else None
            ),
        }
    report["status"] = "completed"
    report["finished_at"] = datetime.now(UTC).isoformat()
    _write(output, report)
    return report


def run_ollama(
    model_name: str, output: Path, seed: int = 0, max_tokens: int = 256, answer_schema: bool = False
) -> dict:
    import httpx
    from openai import OpenAI

    from morph.providers import OpenAICompatibleModel

    if output.exists():
        raise FileExistsError(output)
    with httpx.Client(trust_env=False, timeout=120) as transport:
        inventory = transport.get("http://127.0.0.1:11434/api/tags")
        inventory.raise_for_status()
        selected = next((m for m in inventory.json()["models"] if m["name"] == model_name), None)
        if (
            not selected
            or not selected.get("digest")
            or selected.get("remote_model")
            or selected.get("remote_host")
        ):
            raise ValueError("an already installed local model is required")
        version = transport.get("http://127.0.0.1:11434/api/version")
        version.raise_for_status()
        with OpenAI(
            api_key="ollama-local",
            base_url="http://127.0.0.1:11434/v1/",
            max_retries=0,
            http_client=transport,
        ) as client:
            schema = (
                {
                    "type": "object",
                    "properties": {"answer": {"type": "integer"}},
                    "required": ["answer"],
                    "additionalProperties": False,
                }
                if answer_schema
                else None
            )
            model = OpenAICompatibleModel(
                client,
                model_name,
                input_per_million=0,
                output_per_million=0,
                temperature=0,
                seed=seed,
                max_tokens=max_tokens,
                json_mode=not answer_schema,
                response_schema=schema,
            )
            report = measure(
                model,
                {
                    "model": model_name,
                    "digest": selected["digest"],
                    "ollama_version": version.json()["version"],
                    "seed": seed,
                    "temperature": 0,
                    "max_tokens": max_tokens,
                    "json_mode": not answer_schema,
                    "response_schema": schema,
                    "endpoint": "http://127.0.0.1:11434/v1/",
                    "retries": 0,
                },
                output,
            )
            runtime = transport.get("http://127.0.0.1:11434/api/ps")
            runtime.raise_for_status()
            report["runtime_models"] = runtime.json()
            _write(output, report)
            return report
