from morph.benchmark import RetryAgent, benchmark
from morph.core import Run, Task
from morph.demo import MockAgent, Patch


def test_benchmark_compares_strategies_and_preserves_unknown_costs():
    class UnknownCostAgent:
        def run(self, task):
            return Run(task.id, sum(task.values), 0.5, model_calls=1)

    tasks = [Task("v1", "a", "validation", (-2, 1), -1), Task("v2", "a", "validation", (1, 2), 3)]
    report = benchmark(
        {
            "baseline": MockAgent(),
            "tool": MockAgent(Patch("p", "h", "signed_sum")),
            "model": UnknownCostAgent(),
        },
        tasks,
        baseline_name="baseline",
    )
    assert report["strategies"]["baseline"]["success_rate"] == 0.5
    assert report["strategies"]["tool"]["success_rate"] == 1.0
    assert report["strategies"]["tool"]["improvements"] == 1
    assert report["strategies"]["model"]["total_cost_usd"] is None
    assert report["strategies"]["model"]["model_calls"] == 2


def test_retry_accumulates_calls_cost_and_returns_last_attempt():
    class Agent:
        def __init__(self):
            self.count = 0

        def run(self, task):
            self.count += 1
            return Run(task.id, self.count, 0.1, model_calls=1, cost_usd=0.25)

    result = RetryAgent(Agent(), attempts=2).run(Task("t", "a", "validation", (1,), 1))
    assert result.answer == 2
    assert result.model_calls == 2
    assert result.cost_usd == 0.5
