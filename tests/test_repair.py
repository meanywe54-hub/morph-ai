import json
import subprocess

import pytest

from morph.core import Task
from morph.repair import repair_function


class Generator:
    def __init__(self, code):
        self.code = code
        self.prompts = []

    def complete(self, prompt):
        self.prompts.append(prompt)
        return json.dumps({"code": self.code})


SOURCE = "VALUE = 3\n\ndef batches(items, size):\n    return items // size\n\n# Keep this.\n"
FIX = "def batches(items, size):\n    return (items + size - 1) // size"


def cases():
    return [
        Task("development-example", "repair", "development", (5, 2), 3),
        *(Task(f"validation-{i}", "repair", "validation", (i, 3), (i + 2) // 3) for i in range(20)),
    ]


def test_repairs_a_project_function_and_excludes_validation_from_prompt():
    model = Generator(FIX)
    report = repair_function(model, "src/billing.py", SOURCE, "batches", cases())
    assert report["status"] == "eligible_for_review"
    assert report["validation"]["candidate_success"] == 1
    assert report["validation"]["baseline_success"] < 1
    assert report["validation"]["regressions"] == 0
    assert report["patch"].startswith("--- a/src/billing.py\n+++ b/src/billing.py\n")
    assert "+    return (items + size - 1) // size\n" in report["patch"]
    assert len(model.prompts) == 1
    assert "validation-" not in model.prompts[0]
    assert "VALUE = 3" not in model.prompts[0]


@pytest.mark.parametrize(
    "code",
    [
        "def batches(items, size=4):\n    return 0",
        "def batches(items, size):\n    return __import__('os').getcwd()",
        FIX + "\n\nVALUE = 9",
    ],
)
def test_rejects_changes_outside_repair_contract(code):
    report = repair_function(Generator(code), "billing.py", SOURCE, "batches", cases())
    assert report["status"] == "candidate_rejected"
    assert "patch" not in report


def test_regressing_candidate_produces_no_patch():
    model = Generator("def batches(items, size):\n    return 3")
    report = repair_function(model, "billing.py", SOURCE, "batches", cases())
    assert report["status"] == "rejected"
    assert report["validation"]["regressions"] > 0
    assert "patch" not in report


def test_candidate_must_also_fix_the_reproduced_bug():
    model = Generator(
        "def batches(items, size):\n"
        "    if size == 2:\n        return items // size\n"
        "    return (items + size - 1) // size"
    )
    report = repair_function(model, "billing.py", SOURCE, "batches", cases())
    assert report["status"] == "development_failed"
    assert "patch" not in report


def test_retry_receives_only_development_feedback():
    class RetryModel(Generator):
        def complete(self, prompt):
            self.prompts.append(prompt)
            code = SOURCE.split("\n\n")[1] if len(self.prompts) == 1 else FIX
            return json.dumps({"code": code})

    model = RetryModel(FIX)
    report = repair_function(model, "billing.py", SOURCE, "batches", cases(), attempts=2)
    assert report["status"] == "eligible_for_review"
    assert report["generation"]["calls"] == 2
    assert '"observed": 2' in model.prompts[1]
    assert "validation-" not in model.prompts[1]


def test_split_overlap_is_refused_before_model_call():
    model = Generator(FIX)
    overlapping = [*cases(), Task("new-id", "repair", "validation", (5, 2), 3)]
    with pytest.raises(ValueError, match="overlap"):
        repair_function(model, "billing.py", SOURCE, "batches", overlapping)
    assert not model.prompts


def test_patch_applies_to_windows_crlf_without_changing_line_endings(tmp_path):
    source = SOURCE.replace("\n", "\r\n")
    project_file = tmp_path / "billing.py"
    project_file.write_bytes(source.encode())
    report = repair_function(Generator(FIX), "billing.py", source, "batches", cases())
    patch = tmp_path / "repair.diff"
    patch.write_bytes(report["patch"].encode())
    subprocess.run(
        ["git", "-c", "core.autocrlf=false", "apply", "--no-index", patch.name],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    updated = project_file.read_bytes()
    assert b"return (items + size - 1) // size\r\n" in updated
    assert b"\n" not in updated.replace(b"\r\n", b"")


def test_native_probe_rejects_an_encoding_cookie():
    from examples.python_repair import native_check

    updated = "# coding: utf-7\n" + SOURCE.replace(
        "return items // size", "return (items + size - 1) // size"
    )
    with pytest.raises(ValueError, match="outside the selected"):
        native_check(SOURCE, updated, "batches", lambda items, size: 3, [[(5, 2)]])


def test_native_probe_accepts_a_utf8_docstring():
    from examples.python_repair import native_check

    updated = SOURCE.replace(
        "return items // size", '"""Count boxes 🔧."""\n    return (items + size - 1) // size'
    )
    assert native_check(SOURCE, updated, "batches", lambda items, size: 3, [[(5, 2)]]) == 1


def test_separate_holdout_checks_same_candidate_once(tmp_path):
    model = Generator(FIX)
    holdout = [
        Task("holdout-one", "repair", "holdout", (26, 5), 6),
        Task("holdout-two", "repair", "holdout", (30, 5), 6),
    ]
    ledger = tmp_path / "ledger.db"
    report = repair_function(
        model, "billing.py", SOURCE, "batches", cases(), holdout=holdout, ledger=ledger
    )
    assert report["holdout"]["candidate_success"] == 1
    assert report["holdout"]["baseline_success"] == 0.5
    assert "holdout-one" not in model.prompts[0]
    with pytest.raises(ValueError, match="already used"):
        repair_function(
            model, "billing.py", SOURCE, "batches", cases(), holdout=holdout, ledger=ledger
        )
