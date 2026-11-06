import pytest

from morph.core import Task
from morph.demo import MockAgent, Patch
from morph.experiment import compare, evaluate
from morph.registry import activate, register_patch
from morph.router import route


def test_router_uses_only_active_patch_with_sufficient_category_evidence(tmp_path):
    db = tmp_path / "registry.db"
    patch = Patch("p", "sign", "signed_sum")
    tasks = [Task(str(i), "arithmetic", "validation", (-i - 1, 1), -i) for i in range(20)]
    comparison = compare(evaluate(MockAgent(), tasks), evaluate(MockAgent(patch), tasks))
    report = {"patch": {"id": "p"}, "comparison": comparison}
    assert route(db, "arithmetic", report)["use_patch"] is False
    register_patch(
        db, {"id": "p", "operation": "signed_sum"}, comparison["status"], evidence=comparison
    )
    activate(db, "p", approved_by="reviewer", reason="reviewed")
    assert route(db, "arithmetic", report)["use_patch"] is True
    assert route(db, "unknown", report)["use_patch"] is False
    assert route(db, "arithmetic", report, max_cost_usd=0.0)["use_patch"] is True
    report["comparison"]["candidate_runs"][0]["run"]["elapsed_s"] += 10
    assert route(db, "arithmetic", report)["use_patch"] is False


def test_router_declines_when_budget_cannot_be_evaluated(tmp_path):
    db = tmp_path / "registry.db"
    patch = Patch("p", "sign", "signed_sum")
    tasks = [Task(str(i), "arithmetic", "validation", (-i - 1, 1), -i) for i in range(20)]
    comparison = compare(evaluate(MockAgent(), tasks), evaluate(MockAgent(patch), tasks))
    for observation in comparison["candidate_runs"]:
        observation["run"]["cost_usd"] = None
    register_patch(
        db, {"id": "p", "operation": "signed_sum"}, comparison["status"], evidence=comparison
    )
    activate(db, "p", approved_by="reviewer", reason="reviewed")
    report = {"patch": {"id": "p"}, "comparison": comparison}
    assert route(db, "arithmetic", report, max_cost_usd=1)["use_patch"] is False


def test_router_rejects_evidence_with_inconsistent_pass_flags(tmp_path):
    db = tmp_path / "registry.db"
    patch = Patch("p", "sign", "signed_sum")
    tasks = [Task(str(i), "arithmetic", "validation", (-i - 1, 1), -i) for i in range(20)]
    comparison = compare(evaluate(MockAgent(), tasks), evaluate(MockAgent(patch), tasks))
    comparison["candidate_runs"][0]["run"]["answer"] = 999
    with pytest.raises(ValueError, match="evidence"):
        register_patch(
            db, {"id": "p", "operation": "signed_sum"}, comparison["status"], evidence=comparison
        )


def test_registry_rejects_different_patch_with_same_id(tmp_path):
    db = tmp_path / "registry.db"
    patch = Patch("p", "sign", "signed_sum")
    tasks = [Task(str(i), "arithmetic", "validation", (-i - 1, 1), -i) for i in range(20)]
    comparison = compare(evaluate(MockAgent(), tasks), evaluate(MockAgent(patch), tasks))
    with pytest.raises(ValueError, match="patch"):
        register_patch(
            db,
            {"id": "p", "operation": "something_else"},
            comparison["status"],
            evidence=comparison,
        )


def test_registry_rejects_different_source_agent(tmp_path):
    db = tmp_path / "registry.db"
    patch = Patch("p", "sign", "signed_sum")
    tasks = [Task(str(i), "arithmetic", "validation", (-i - 1, 1), -i) for i in range(20)]
    comparison = compare(evaluate(MockAgent(), tasks), evaluate(MockAgent(patch), tasks))
    with pytest.raises(ValueError, match="patch"):
        register_patch(
            db,
            {"id": "p", "operation": "signed_sum", "source_agent": "openai:other"},
            comparison["status"],
            evidence=comparison,
        )
