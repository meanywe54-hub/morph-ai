"""A deterministic infrastructure demonstration, not an LLM experiment."""

from dataclasses import asdict, dataclass
from time import perf_counter

from morph.core import Run, Task
from morph.experiment import compare, diagnose, evaluate
from morph.patches import patch_fingerprint


@dataclass(frozen=True)
class Patch:
    id: str
    hypothesis: str
    operation: str
    source_agent: str = "mock-absolute-sum-v1"
    status: str = "candidate"


class MockAgent:
    def __init__(self, patch: Patch | None = None):
        if patch is not None and patch.operation != "signed_sum":
            raise ValueError("unsupported operation")
        self.patch = patch

    def run(self, task: Task) -> Run:
        start = perf_counter()
        if self.patch:
            answer = sum(task.values)
            trace = (
                f"patch:{self.patch.id}",
                f"sha256:{patch_fingerprint(asdict(self.patch))}",
                "trusted signed_sum operation",
            )
        else:
            answer = sum(abs(x) for x in task.values)
            trace = ("mock agent used absolute values",)
        return Run(task.id, answer, perf_counter() - start, trace=trace, cost_usd=0.0)


def mock_synthesize(diagnosis: dict) -> Patch:
    if diagnosis["failures"] == 0:
        raise ValueError("no failures to diagnose")
    # Fixed response stands in for a model. It is not autonomous code generation.
    return Patch("mock-signed-sum-v1", diagnosis["hypothesis"], "signed_sum")


def tasks() -> tuple[list[Task], list[Task]]:
    development = [
        Task("dev-1", "arithmetic", "development", (5, -2), 3),
        Task("dev-2", "arithmetic", "development", (-4, 1), -3),
    ]
    validation = [
        Task("val-1", "ledger", "validation", (12, -7), 5),
        Task("val-2", "ledger", "validation", (-3, 8, -1), 4),
        Task("val-3", "inventory", "validation", (10, -4, -3), 3),
        Task("val-4", "inventory", "validation", (2, 3), 5),
    ]
    return development, validation


def synthesis_tasks() -> tuple[list[Task], list[Task]]:
    """Larger synthetic split for exercising the review gate, not a research benchmark."""
    development, _ = tasks()
    validation = []
    for category, offset in (("ledger", 100), ("inventory", 200)):
        for i in range(20):
            values = (offset + i, -i - 1 if i % 2 else i + 1)
            validation.append(Task(f"{category}-{i}", category, "validation", values, sum(values)))
    return development, validation


def run_demo() -> dict:
    development, validation = tasks()
    diagnosis = diagnose(evaluate(MockAgent(), development))
    patch = mock_synthesize(diagnosis)
    comparison = compare(evaluate(MockAgent(), validation), evaluate(MockAgent(patch), validation))
    return {
        "mode": "synthetic mock; no LLM or generated code",
        "diagnosis": diagnosis,
        "patch": asdict(patch),
        "comparison": comparison,
    }
