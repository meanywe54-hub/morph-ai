"""Paired evaluation and a conservative decision rule."""

from collections import Counter
from dataclasses import asdict, dataclass
from time import perf_counter

from morph.core import AgentAdapter, Run, Task


@dataclass(frozen=True)
class Observation:
    task_id: str
    category: str
    split: str
    expected: int
    run: Run
    passed: bool
    values: tuple[int, ...] = ()


def evaluate(agent: AgentAdapter, tasks: list[Task]) -> list[Observation]:
    results = []
    for task in tasks:
        start = perf_counter()
        try:
            # Do not disclose answers to the agent.
            public_task = Task(task.id, task.category, task.split, task.values, 0)
            run = agent.run(public_task)
            if run.task_id != task.id:
                raise ValueError("agent returned the wrong task id")
        except Exception as exc:  # noqa: BLE001 - adapters are an isolation boundary for failures
            run = Run(task.id, None, perf_counter() - start, error=type(exc).__name__)
        results.append(
            Observation(
                task.id,
                task.category,
                task.split,
                task.expected,
                run,
                run.error is None and run.answer == task.expected,
                task.values,
            )
        )
    return results


def diagnose(observations: list[Observation]) -> dict:
    failures = [x for x in observations if not x.passed]
    return {
        "failures": len(failures),
        "categories": dict(Counter(x.category for x in failures)),
        "hypothesis": "Signed inputs may be mishandled" if failures else "No failure observed",
        "evidence": [x.task_id for x in failures],
    }


def compare(baseline: list[Observation], candidate: list[Observation], min_tasks: int = 20) -> dict:
    if not baseline or len(baseline) != len(candidate):
        raise ValueError("paired results must be nonempty and equal length")
    if len({x.task_id for x in baseline}) != len(baseline):
        raise ValueError("task IDs must be unique")
    for a, b in zip(baseline, candidate, strict=True):
        if (a.task_id, a.split, a.category, a.expected, a.values) != (
            b.task_id,
            b.split,
            b.category,
            b.expected,
            b.values,
        ):
            raise ValueError("results are not paired")
        if a.split != "validation":
            raise ValueError("selection is restricted to validation tasks")
    n = len(baseline)
    gains = sum(not a.passed and b.passed for a, b in zip(baseline, candidate, strict=True))
    regressions = sum(a.passed and not b.passed for a, b in zip(baseline, candidate, strict=True))
    categories = {}
    for category in sorted({x.category for x in baseline}):
        pairs = [(a, b) for a, b in zip(baseline, candidate, strict=True) if a.category == category]
        categories[category] = {
            "n": len(pairs),
            "baseline": sum(a.passed for a, _ in pairs),
            "candidate": sum(b.passed for _, b in pairs),
        }
    # This is an operational rule, not a statistical significance claim.
    if regressions or any(x["candidate"] < x["baseline"] for x in categories.values()):
        status = "rejected"
    elif (
        n < min_tasks
        or len({x.values for x in baseline}) < min_tasks
        or gains == 0
        or any(x.run.error for x in baseline + candidate)
    ):
        status = "inconclusive"
    else:
        status = "eligible_for_review"
    return {
        "n": n,
        "baseline_success": sum(x.passed for x in baseline) / n,
        "candidate_success": sum(x.passed for x in candidate) / n,
        "improvements": gains,
        "regressions": regressions,
        "categories": categories,
        "status": status,
        "reason": "validation only; manual approval required",
        "baseline_runs": [asdict(x) for x in baseline],
        "candidate_runs": [asdict(x) for x in candidate],
    }
