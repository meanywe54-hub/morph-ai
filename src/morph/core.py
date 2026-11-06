"""Small, provider-independent task and agent contracts."""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Task:
    id: str
    category: str
    split: str
    values: tuple[int, ...]
    expected: int


@dataclass(frozen=True)
class Run:
    task_id: str
    answer: int | None
    elapsed_s: float
    error: str | None = None
    trace: tuple[str, ...] = ()
    model_calls: int = 0
    cost_usd: float | None = None
    metadata: dict[str, str] = field(default_factory=dict)


class AgentAdapter(Protocol):
    def run(self, task: Task) -> Run:
        """Run a task without consulting its expected answer."""
        ...
