import pytest

from morph.core import Task
from morph.demo import MockAgent, Patch
from morph.experiment import compare, evaluate
from morph.registry import activate, active_patch, register_patch, rollback


def evidence(patch_id):
    tasks = [Task(str(i), "a", "validation", (-i - 1, 1), -i) for i in range(20)]
    return compare(
        evaluate(MockAgent(), tasks), evaluate(MockAgent(Patch(patch_id, "h", "signed_sum")), tasks)
    )


def test_activation_requires_eligible_evidence_and_explicit_approval(tmp_path):
    db = tmp_path / "registry.db"
    register_patch(db, {"id": "p1", "code": "pass"}, "inconclusive")
    with pytest.raises(ValueError, match="eligible"):
        activate(db, "p1", approved_by="reviewer", reason="approved")
    with pytest.raises(ValueError, match="evidence"):
        register_patch(db, {"id": "no-evidence"}, "eligible_for_review")
    with pytest.raises(ValueError, match="patch"):
        register_patch(
            db,
            {"id": "p2", "operation": "signed_sum"},
            "eligible_for_review",
            evidence=evidence("other"),
        )
    register_patch(
        db, {"id": "p2", "operation": "signed_sum"}, "eligible_for_review", evidence=evidence("p2")
    )
    with pytest.raises(ValueError, match="approval"):
        activate(db, "p2", approved_by="", reason="approved")
    activate(db, "p2", approved_by="reviewer", reason="reviewed")
    assert active_patch(db)["id"] == "p2"


def test_rollback_restores_previously_active_version(tmp_path):
    db = tmp_path / "registry.db"
    for patch in ("p1", "p2"):
        register_patch(
            db,
            {"id": patch, "operation": "signed_sum"},
            "eligible_for_review",
            evidence=evidence(patch),
        )
        activate(db, patch, approved_by="reviewer", reason="reviewed")
    rollback(db, "p1", approved_by="reviewer", reason="regression")
    assert active_patch(db)["id"] == "p1"
    rollback(db, None, approved_by="reviewer", reason="disable")
    assert active_patch(db) is None


def test_rollback_cannot_activate_version_that_was_never_active(tmp_path):
    db = tmp_path / "registry.db"
    register_patch(
        db, {"id": "p1", "operation": "signed_sum"}, "eligible_for_review", evidence=evidence("p1")
    )
    with pytest.raises(ValueError, match="previously active"):
        rollback(db, "p1", approved_by="reviewer", reason="test")
