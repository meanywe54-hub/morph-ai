"""Model-backed adapter for MORPH's narrow integer-sum task contract."""

import json
from time import perf_counter

from morph.core import Run, Task
from morph.patches import TextModel


class ModelAgent:
    def __init__(self, model: TextModel):
        self.model = model

    def run(self, task: Task) -> Run:
        start = perf_counter()
        prompt = (
            "Add all of the following signed integers. Return only a JSON object "
            "with an integer field named answer. Integers: " + json.dumps(task.values)
        )
        answer = None
        error = None
        try:
            response = self.model.complete(prompt)
            result = json.loads(response)
            answer = result["answer"]
            if type(answer) is not int:
                raise ValueError("answer must be an integer")
        except Exception as exc:  # noqa: BLE001 - preserve failed model calls as observations
            answer = None
            error = type(exc).__name__
        usage = getattr(self.model, "last_usage", None)
        cost = usage.get("cost_usd") if isinstance(usage, dict) else None
        metadata = {
            key: str(usage[key])
            for key in ("input_tokens", "output_tokens")
            if isinstance(usage, dict) and key in usage
        }
        return Run(
            task.id,
            answer,
            perf_counter() - start,
            error=error,
            trace=("model arithmetic request",),
            model_calls=1,
            cost_usd=cost,
            metadata=metadata,
        )
