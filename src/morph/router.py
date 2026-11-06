"""Transparent routing based on reviewed patches and validation evidence."""

import math
from pathlib import Path

from morph.registry import active_patch, matches_evidence


def route(
    db_path: Path,
    category: str,
    report: dict,
    *,
    min_samples: int = 20,
    max_cost_usd: float | None = None,
    max_elapsed_s: float | None = None,
) -> dict:
    """Choose whether the caller may use the active patch; no code runs here."""

    def decline(reason: str) -> dict:
        return {"use_patch": False, "reason": reason}

    if min_samples < 1 or any(
        x is not None and (not math.isfinite(x) or x < 0) for x in (max_cost_usd, max_elapsed_s)
    ):
        raise ValueError("invalid routing limits")
    patch = active_patch(db_path)
    if patch is None:
        return decline("no active patch")
    try:
        if report["patch"]["id"] != patch["id"]:
            return decline("evidence does not match active patch")
        comparison = report["comparison"]
        if not matches_evidence(db_path, patch["id"], comparison):
            return decline("evidence differs from the reviewed record")
        if comparison["status"] != "eligible_for_review":
            return decline("validation is not eligible")
        baseline, candidate = comparison["baseline_runs"], comparison["candidate_runs"]
        if not baseline or len(baseline) != len(candidate):
            return decline("invalid paired evidence")
        seen = set()
        pairs = []
        for a, b in zip(baseline, candidate, strict=True):
            keys = ("task_id", "split", "category", "values", "expected")
            if any(a[k] != b[k] for k in keys) or a["split"] != "validation":
                return decline("invalid paired evidence")
            if a["task_id"] in seen:
                return decline("duplicate task ID")
            for observation in (a, b):
                run = observation["run"]
                actual_pass = run["error"] is None and run["answer"] == observation["expected"]
                if type(observation["passed"]) is not bool or observation["passed"] != actual_pass:
                    return decline("inconsistent evaluation result")
            seen.add(a["task_id"])
            if a["category"] == category:
                pairs.append((a, b))
        if len(pairs) < min_samples or len({tuple(a["values"]) for a, _ in pairs}) < min_samples:
            return decline("insufficient category evidence")
        if any(a["run"]["error"] is not None or b["run"]["error"] is not None for a, b in pairs):
            return decline("evaluation errors")
        if any(a["passed"] and not b["passed"] for a, b in pairs):
            return decline("category regressions observed")
        if sum(b["passed"] for _, b in pairs) <= sum(a["passed"] for a, _ in pairs):
            return decline("no measured category improvement")
        for field, limit in (("cost_usd", max_cost_usd), ("elapsed_s", max_elapsed_s)):
            if limit is not None:
                values = [b["run"][field] for _, b in pairs]
                if any(
                    not isinstance(x, (int, float)) or not math.isfinite(x) or x < 0 for x in values
                ):
                    return decline(f"{field} unavailable")
                if sum(values) / len(values) > limit:
                    return decline(f"{field} limit exceeded")
    except (KeyError, TypeError, ValueError):
        return decline("malformed evidence")
    return {
        "use_patch": True,
        "patch_id": patch["id"],
        "reason": f"{len(pairs)} validation tasks in category, no observed regressions",
    }
