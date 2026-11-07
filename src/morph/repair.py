"""Propose and verify a patch to one bounded integer function in a Python module."""

import ast
import difflib
import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

from morph.bounded import BoundedIntegerFunction
from morph.core import Run, Task
from morph.experiment import Observation, compare, evaluate
from morph.holdout import evaluate_once
from morph.patches import TextModel
from morph.sandbox import SandboxFailure

CODE_SCHEMA = {
    "type": "object",
    "properties": {"code": {"type": "string"}},
    "required": ["code"],
    "additionalProperties": False,
}


def _source_path(path: str) -> str:
    parts = path.split("/")
    if not path.endswith(".py") or any(
        not re.fullmatch(r"[A-Za-z0-9_.-]+", part) or part in {".", ".."} for part in parts
    ):
        raise ValueError("source must be a relative .py path with plain path segments")
    return path


def _read(path: Path, limit: int, encoding: str = "utf-8-sig") -> str:
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("input file exceeds the size limit")
    return raw.decode(encoding)


def read_cases(path: Path, split: str) -> list[Task]:
    rows = json.loads(_read(path, 200_000))
    if not isinstance(rows, list) or not 1 <= len(rows) <= 1000:
        raise ValueError("expected a JSON array of 1 to 1000 cases")
    tasks = []
    for row in rows:
        if (
            not isinstance(row, dict)
            or row.keys() != {"id", "values", "expected"}
            or not isinstance(row["id"], str)
            or not isinstance(row["values"], list)
        ):
            raise ValueError("each case requires id, values and expected")
        tasks.append(Task(row["id"], "python-repair", split, tuple(row["values"]), row["expected"]))
    return tasks


class _FunctionAgent:
    def __init__(self, function: BoundedIntegerFunction):
        self.function = function

    def run(self, task: Task) -> Run:
        start = perf_counter()
        answer = self.function.run(task.values).answer
        return Run(task.id, answer, perf_counter() - start, cost_usd=0.0)


def _check_cases(tasks: list[Task], holdout: list[Task], arity: int) -> None:
    all_tasks = tasks + holdout
    if (
        not any(task.split == "development" for task in tasks)
        or sum(task.split == "validation" for task in tasks) < 20
        or any(task.split not in {"development", "validation"} for task in tasks)
        or any(task.split != "holdout" for task in holdout)
    ):
        raise ValueError("repair requires development and at least 20 validation cases")
    if any(
        not task.id.strip()
        or len(task.values) != arity
        or any(type(value) is not int or abs(value) > 10**9 for value in task.values)
        or type(task.expected) is not int
        or abs(task.expected) > 10**12
        for task in all_tasks
    ):
        raise ValueError("invalid case ID, integer arguments or expected result")
    if len({task.id for task in all_tasks}) != len(all_tasks) or len(
        {task.values for task in all_tasks}
    ) != len(all_tasks):
        raise ValueError("case IDs and inputs must be distinct with no split overlap")


def _signature(function: ast.FunctionDef) -> tuple:
    return ast.dump(function.args), ast.dump(function.returns) if function.returns else None


def _failures(rows: list[Observation]) -> list[dict]:
    return [
        {"arguments": row.values, "expected": row.expected, "observed": row.run.answer}
        for row in rows
        if not row.passed
    ][:20]


def _propose(model, prompt, target, parameters, development_tasks, attempts, report):
    feedback = ""
    generation = {"calls": 0, "elapsed_s": 0.0, "attempts": []}
    report["generation"] = generation
    for _ in range(attempts):
        start = perf_counter()
        raw = model.complete(prompt + feedback)
        attempt = {"elapsed_s": perf_counter() - start, "status": "candidate_rejected"}
        generation["calls"] += 1
        generation["elapsed_s"] += attempt["elapsed_s"]
        generation["attempts"].append(attempt)
        usage = getattr(model, "last_usage", None)
        if isinstance(usage, dict):
            attempt.update(
                {
                    key: usage[key]
                    for key in ("input_tokens", "output_tokens")
                    if type(usage.get(key)) is int
                }
            )
        try:
            if not isinstance(raw, str) or len(raw.encode()) > 32_000:
                raise ValueError("invalid response size")
            response = json.loads(raw)
            if not isinstance(response, dict) or response.keys() != {"code"}:
                raise ValueError("expected a single code field")
            code = response["code"]
            candidate = _FunctionAgent(BoundedIntegerFunction(code, target.name, parameters))
            replacement = ast.parse(code).body[0]
            if _signature(replacement) != _signature(target):
                raise ValueError("replacement changes the function signature")
        except (SandboxFailure, SyntaxError, ValueError, RecursionError) as exc:
            report["status"] = "candidate_rejected"
            report["error"] = str(exc)
            feedback = "\nThe previous response was rejected. Follow the schema and syntax rules."
            continue
        failures = _failures(evaluate(candidate, development_tasks))
        report.pop("error", None)
        if not failures:
            attempt["status"] = "development_passed"
            return candidate, replacement
        attempt["status"] = report["status"] = "development_failed"
        feedback = "\nThe previous code failed these development examples. Correct its logic.\n"
        feedback += json.dumps({"previous_code": code[:1600], "failures": failures[:4]})
    return None


def repair_function(
    model: TextModel,
    path: str,
    source: str,
    name: str,
    tasks: list[Task],
    *,
    description: str = "",
    attempts: int = 1,
    holdout: list[Task] | None = None,
    ledger: Path | None = None,
) -> dict:
    """Evaluate a generated replacement and return an unapplied patch when eligible."""
    _source_path(path)
    if bool(holdout) != (ledger is not None):
        raise ValueError("holdout and ledger must be supplied together")
    if len(description) > 2000:
        raise ValueError("repair description exceeds the size limit")
    if type(attempts) is not int or not 1 <= attempts <= 2:
        raise ValueError("repair supports one or two generation attempts")
    encoded = source.encode("utf-8")
    if len(encoded) > 200_000 or not source.endswith("\n"):
        raise ValueError("repair source must be UTF-8 text with a final newline")
    newline = "\r\n" if "\r\n" in source else "\n"
    if newline == "\r\n" and source.count("\r\n") != source.count("\n"):
        raise ValueError("repair source uses mixed line endings")
    source = source.replace("\r\n", "\n")
    if "\r" in source:
        raise ValueError("repair source must use LF or CRLF line endings")
    try:
        module = ast.parse(source)
        compile(module, "<repair source>", "exec")
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise ValueError("invalid Python module") from exc
    targets = [
        node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    if len(targets) != 1 or targets[0].decorator_list:
        raise ValueError("exactly one undecorated top-level target function is required")
    target = targets[0]
    parameters = tuple(arg.arg for arg in target.args.args)
    _check_cases(tasks, holdout or [], len(parameters))
    lines = [line + "\n" for line in source.split("\n")[:-1]]
    start, end = target.lineno - 1, target.end_lineno
    original = "".join(lines[start:end])
    baseline = _FunctionAgent(BoundedIntegerFunction(original, name, parameters))
    development_tasks = [task for task in tasks if task.split == "development"]
    development = evaluate(baseline, development_tasks)
    failures = _failures(development)
    if any(row.run.error for row in development):
        raise ValueError("baseline must execute successfully on development cases")
    if not failures:
        raise ValueError("development cases must reproduce a bug")
    validation = [task for task in tasks if task.split == "validation"]
    baseline_validation = evaluate(baseline, validation)
    if any(row.run.error for row in baseline_validation):
        raise ValueError("baseline must execute successfully on validation cases")
    prompt = (
        "Repair the Python function from the failing examples. Return a JSON object with only "
        "a code field containing the complete function with the same name and signature. "
        "Arguments and return are integers. Use assignments, if/else, comparisons, return "
        "and integer operators + - * // %. No calls, imports, loops or other definitions.\n"
        + json.dumps({"description": description, "function": original, "failures": failures})
    )
    if len(prompt.encode()) > 8000:
        raise ValueError("repair prompt exceeds the size limit")
    report = {
        "status": "candidate_rejected",
        "source_sha256": hashlib.sha256(encoded).hexdigest(),
        "function": name,
        "runtime": "bounded-integer-function-v1",
        "baseline_validation": {
            "n": len(baseline_validation),
            "correct": sum(row.passed for row in baseline_validation),
        },
    }
    result = _propose(model, prompt, target, parameters, development_tasks, attempts, report)
    if result is None:
        return report
    candidate, replacement = result
    updated = "".join([*lines[:start], ast.unparse(replacement) + "\n", *lines[end:]])
    try:
        compile(updated, "<patched module>", "exec")
    except (SyntaxError, ValueError, RecursionError) as exc:
        report["status"] = "candidate_rejected"
        report["error"] = str(exc)
        return report
    comparison = compare(baseline_validation, evaluate(candidate, validation))
    report["validation"] = {
        key: value for key, value in comparison.items() if not key.endswith("_runs")
    }
    report["status"] = comparison["status"]
    if report["status"] != "eligible_for_review":
        return report
    if comparison["candidate_success"] != 1:
        report["status"] = "validation_failed"
        return report
    if holdout:
        dataset = json.dumps([asdict(task) for task in holdout], sort_keys=True).encode()
        report["holdout"] = evaluate_once(
            ledger,
            hashlib.sha256(dataset).hexdigest(),
            baseline,
            candidate,
            holdout,
            metadata={
                "candidate_sha256": hashlib.sha256(
                    updated.replace("\n", newline).encode()
                ).hexdigest()
            },
        )
        result = report["holdout"]
        if (
            result["candidate_success"] != 1
            or result["regressions"]
            or result["baseline_errors"]
            or result["candidate_errors"]
        ):
            report["status"] = "holdout_failed"
            return report
    report["patch"] = "".join(
        difflib.unified_diff(
            [line[:-1] + newline for line in lines],
            [line + newline for line in updated.split("\n")[:-1]],
            f"a/{path}",
            f"b/{path}",
        )
    )
    return report


class OllamaRepairModel:
    """Native Ollama JSON-schema client using only the local interface."""

    endpoint = "http://127.0.0.1:11434"

    def __init__(self, client, name: str):
        self.client = client
        self.name = name
        self.last_usage = None
        self.options = {
            "seed": 0,
            "temperature": 0,
            "num_predict": 320,
            "num_ctx": 4096,
            "num_gpu": 0,
        }
        response = client.get(self.endpoint + "/api/tags")
        response.raise_for_status()
        selected = next((m for m in response.json()["models"] if m["name"] == name), None)
        if (
            not selected
            or not selected.get("digest")
            or selected.get("remote_host")
            or selected.get("remote_model")
        ):
            raise ValueError("an already installed local model is required")
        response = client.get(self.endpoint + "/api/version")
        response.raise_for_status()
        self.configuration = {
            "model": name,
            "digest": selected["digest"],
            "ollama_version": response.json()["version"],
            "think": False,
            "options": self.options,
        }

    def complete(self, prompt: str) -> str:
        self.last_usage = None
        response = self.client.post(
            self.endpoint + "/api/chat",
            json={
                "model": self.name,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "think": False,
                "format": CODE_SCHEMA,
                "options": self.options,
            },
        )
        response.raise_for_status()
        result = response.json()
        self.last_usage = {
            "input_tokens": result.get("prompt_eval_count"),
            "output_tokens": result.get("eval_count"),
        }
        return result["message"]["content"]


def run_local_repair(args) -> dict:
    import httpx

    if bool(args.holdout) != bool(args.ledger):
        raise ValueError("--holdout and --ledger must be supplied together")
    root = args.project.resolve(strict=True)
    relative = _source_path(args.source)
    file = root.joinpath(*relative.split("/"))
    if file.resolve(strict=True) != file or not file.is_file():
        raise ValueError("source must be a regular file inside the project without symlinks")
    inputs = [file, args.development, args.validation]
    outputs = [args.report, args.patch]
    if args.holdout:
        inputs.append(args.holdout)
        outputs.append(args.ledger)
    paths = [path.resolve() for path in inputs + outputs]
    if len(set(paths)) != len(paths):
        raise ValueError("input and output paths must be distinct")
    for path in (args.report, args.patch):
        if path.exists():
            raise FileExistsError(path)
        if not path.parent.is_dir():
            raise ValueError("output directory must exist")
    source = _read(file, 200_000, "utf-8")
    tasks = read_cases(args.development, "development") + read_cases(args.validation, "validation")
    holdout = read_cases(args.holdout, "holdout") if args.holdout else None
    try:
        with httpx.Client(trust_env=False, timeout=180) as client:
            model = OllamaRepairModel(client, args.model)
            report = repair_function(
                model,
                relative,
                source,
                args.function,
                tasks,
                description=args.description,
                attempts=args.attempts,
                holdout=holdout,
                ledger=args.ledger,
            )
            report["model"] = model.configuration
    except httpx.HTTPError as exc:
        raise ValueError(f"local Ollama request failed: {type(exc).__name__}") from exc
    with args.report.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    if "patch" in report:
        with args.patch.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(report["patch"])
    return report
