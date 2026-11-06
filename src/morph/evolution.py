"""Connect development evidence, synthesis, isolated execution and validation."""

from dataclasses import asdict
from time import perf_counter
from typing import Protocol

from morph.core import AgentAdapter, Run, Task
from morph.experiment import compare, diagnose, evaluate
from morph.patches import CodePatch, TextModel, patch_fingerprint, synthesize
from morph.sandbox import SandboxResult


class Runner(Protocol):
    def run(self, code: str, values: list[int]) -> SandboxResult: ...


class PatchedAgent:
    def __init__(self, patch: CodePatch, runner: Runner):
        if patch.runtime != getattr(runner, "runtime", "docker-python"):
            raise ValueError("patch runtime does not match executor")
        self.patch, self.runner = patch, runner

    def run(self, task: Task) -> Run:
        start = perf_counter()
        result = self.runner.run(self.patch.code, list(task.values))
        return Run(
            task.id,
            result.answer,
            perf_counter() - start,
            trace=(f"patch:{self.patch.id}", f"sha256:{patch_fingerprint(asdict(self.patch))}"),
        )


def evolve(
    agent: AgentAdapter,
    model: TextModel,
    runner: Runner,
    development: list[Task],
    validation: list[Task],
    source_agent: str,
) -> dict:
    if not development or not validation:
        raise ValueError("development and validation tasks are required")
    all_tasks = development + validation
    if len({task.id for task in all_tasks}) != len(all_tasks):
        raise ValueError("task IDs must be unique across splits")
    if {task.values for task in development} & {task.values for task in validation}:
        raise ValueError("task inputs overlap across development and validation")
    if any(t.split != "development" for t in development) or any(
        t.split != "validation" for t in validation
    ):
        raise ValueError("invalid task split")
    dev_results = evaluate(agent, development)
    patch = synthesize(
        model,
        dev_results,
        source_agent,
        instructions=getattr(runner, "synthesis_instructions", None),
        runtime=getattr(runner, "runtime", "docker-python"),
    )
    synthesis_usage = getattr(model, "last_usage", None)
    if isinstance(synthesis_usage, dict):
        synthesis_usage = synthesis_usage.copy()
    baseline = evaluate(agent, validation)
    candidate = evaluate(PatchedAgent(patch, runner), validation)
    return {
        "diagnosis": diagnose(dev_results),
        "patch": asdict(patch),
        "comparison": compare(baseline, candidate),
        "synthesis_usage": synthesis_usage,
        "development_inputs": [list(task.values) for task in development],
        "development_task_ids": [task.id for task in development],
    }
