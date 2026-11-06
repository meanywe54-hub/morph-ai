"""Compare explicitly supplied strategies on the same validation tasks."""

import math
from time import perf_counter

from morph.core import AgentAdapter, Run, Task
from morph.experiment import evaluate


class RetryAgent:
    """Run a fixed number of attempts and return the final result, without an oracle."""

    def __init__(self, agent: AgentAdapter, attempts: int = 2):
        if not 1 <= attempts <= 10:
            raise ValueError("attempts must be between 1 and 10")
        self.agent = agent
        self.attempts = attempts

    def run(self, task: Task) -> Run:
        start = perf_counter()
        runs = [self.agent.run(task) for _ in range(self.attempts)]
        if any(run.task_id != task.id for run in runs):
            raise ValueError("agent returned the wrong task id")
        costs = [x.cost_usd for x in runs]
        total = (
            sum(costs)
            if all(x is not None and math.isfinite(x) and x >= 0 for x in costs)
            else None
        )
        final = runs[-1]
        return Run(
            task.id,
            final.answer,
            perf_counter() - start,
            error=final.error,
            trace=tuple(item for run in runs for item in run.trace),
            model_calls=sum(x.model_calls for x in runs),
            cost_usd=total,
        )


def benchmark(agents: dict[str, AgentAdapter], tasks: list[Task], *, baseline_name: str) -> dict:
    if baseline_name not in agents or not tasks or any(t.split != "validation" for t in tasks):
        raise ValueError("baseline and validation tasks are required")
    if len({t.id for t in tasks}) != len(tasks):
        raise ValueError("task IDs must be unique")
    observations = {name: evaluate(agent, tasks) for name, agent in agents.items()}
    reference = observations[baseline_name]
    result = {}
    for name, runs in observations.items():
        n = len(runs)
        successes = sum(x.passed for x in runs)
        costs = [x.run.cost_usd for x in runs]
        total = (
            sum(costs)
            if all(x is not None and math.isfinite(x) and x >= 0 for x in costs)
            else None
        )
        result[name] = {
            "n": n,
            "successes": successes,
            "success_rate": successes / n,
            "improvements": sum(
                not a.passed and b.passed for a, b in zip(reference, runs, strict=True)
            ),
            "regressions": sum(
                a.passed and not b.passed for a, b in zip(reference, runs, strict=True)
            ),
            "model_calls": sum(x.run.model_calls for x in runs),
            "total_cost_usd": total,
            "cost_per_success_usd": total / successes if total is not None and successes else None,
            "total_elapsed_s": sum(x.run.elapsed_s for x in runs),
            "errors": sum(x.run.error is not None for x in runs),
        }
    return {"baseline": baseline_name, "split": "validation", "strategies": result}
