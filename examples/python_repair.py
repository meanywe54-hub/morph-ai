"""Prepare independent synthetic repair projects and evaluate the local CLI."""

import argparse
import ast
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from morph.bounded import BoundedIntegerFunction


def projects(suite):
    if suite == "followup":
        return {
            "inventory": (
                "pallets_needed",
                "def pallets_needed(parcels, capacity):\n    return parcels // capacity\n",
                (
                    "Return the minimum number of pallets for nonnegative parcels and positive "
                    "capacity. Divide and round up if there is a remainder."
                ),
                lambda parcels, capacity: (parcels + capacity - 1) // capacity,
                [(11, 4), (16, 5), (8, 4)],
                [(50 + 3 * i, 3 + i % 7) for i in range(24)],
                [(400 + 5 * i, 5 + i % 9) for i in range(24)],
            ),
            "payroll": (
                "overtime_minutes",
                (
                    "def overtime_minutes(worked, included):\n"
                    "    if worked > included:\n        return included - worked\n    return 0\n"
                ),
                "Return worked minus included if worked is greater. Return zero otherwise.",
                lambda worked, included: max(worked - included, 0),
                [(92, 60), (55, 50), (21, 30)],
                [(140 + i, 140 + i + i % 7 - 3) for i in range(24)],
                [(600 + i, 600 + i + i % 6 - 3) for i in range(24)],
            ),
            "shipping": (
                "postage",
                (
                    "def postage(weight, allowance):\n"
                    "    if weight < allowance:\n        return 0\n    return 450\n"
                ),
                "Return 450 when weight exceeds the allowance. Equal weight is free.",
                lambda weight, allowance: 450 if weight > allowance else 0,
                [(20, 20), (6, 6), (21, 20)],
                [(60 + i, 60 + i + i % 3 - 1) for i in range(24)],
                [(180 + i, 180 + i + i % 4 - 2) for i in range(24)],
            ),
            "accounting": (
                "net_movement",
                "def net_movement(opening, closing):\n    return opening + closing\n",
                "Return closing minus opening, with its sign.",
                lambda opening, closing: closing - opening,
                [(20, 12), (7, 13), (2, 2)],
                [(-300 + i, -300 + i + i % 5 - 2) for i in range(24)],
                [(750 + i, 750 + i + i % 7 - 3) for i in range(24)],
            ),
        }
    return {
        "warehouse": (
            "box_count",
            "def box_count(items, capacity):\n    return items // capacity\n",
            "Count boxes for nonnegative items and positive capacity. Any remainder needs a box.",
            lambda items, capacity: (items + capacity - 1) // capacity,
            [(9, 4), (3, 8)],
            [(2 * i + 60, 5 + i % 5) for i in range(24)],
            [(3 * i + 300, 4 + i % 11) for i in range(24)],
        ),
        "metering": (
            "remaining_quota",
            (
                "def remaining_quota(used, quota):\n"
                "    if used > quota:\n        return used - quota\n    return quota - used\n"
            ),
            "Return how much quota is left, with a minimum of zero.",
            lambda used, quota: max(quota - used, 0),
            [(17, 12), (33, 19)],
            [(100 + i, 100 + i + i % 5 - 2) for i in range(24)],
            [(300 + i, 300 + i + i % 7 - 3) for i in range(24)],
        ),
        "billing": (
            "late_fee",
            "def late_fee(days, grace):\n    if days >= grace:\n        return 150\n    return 0\n",
            "The flat fee is 150 only when days is strictly greater than the grace period.",
            lambda days, grace: 150 if days > grace else 0,
            [(5, 5), (7, 7)],
            [(30 + i, 30 + i + i % 3 - 1) for i in range(24)],
            [(90 + i, 90 + i + i % 4 - 2) for i in range(24)],
        ),
        "settlement": (
            "balance_change",
            "def balance_change(previous, current):\n    return previous - current\n",
            "Return the signed change in a balance from previous to current.",
            lambda previous, current: current - previous,
            [(14, 9), (3, 10)],
            [(-100 + i, -100 + i + i % 5 - 2) for i in range(24)],
            [(200 + i, 200 + i + i % 7 - 3) for i in range(24)],
        ),
    }


def synthetic_source(project, code):
    return f'"""Synthetic {project} project."""\n\n\n{code}\n\ndef status():\n    return 200\n'


def prepare(root, suite):
    root.mkdir()
    for project, (_, code, _, oracle, *splits) in projects(suite).items():
        project_dir = root / project / "project"
        (project_dir / "src").mkdir(parents=True)
        source = project_dir / "src" / f"{project}.py"
        source.write_text(
            synthetic_source(project, code),
            encoding="utf-8",
            newline="\n",
        )
        for split, arguments in zip(("development", "validation", "holdout"), splits, strict=True):
            rows = [
                {"id": f"{project}-{split}-{i:02}", "values": args, "expected": oracle(*args)}
                for i, args in enumerate(arguments)
            ]
            (root / project / f"{split}.json").write_text(
                json.dumps(rows, indent=2), encoding="utf-8"
            )
    hashes = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
    (root / "inputs.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")


def native_check(original, updated, function, oracle, splits):
    before, after = ast.parse(original), ast.parse(updated)
    target = next(
        node for node in after.body if isinstance(node, ast.FunctionDef) and node.name == function
    )
    parameters = tuple(arg.arg for arg in target.args.args)
    bounded = BoundedIntegerFunction(ast.unparse(target), function, parameters)
    original_target = next(
        node for node in before.body if isinstance(node, ast.FunctionDef) and node.name == function
    )
    original_lines = original.splitlines(keepends=True)
    reconstructed = "".join(
        [
            *original_lines[: original_target.lineno - 1],
            ast.unparse(target) + "\n",
            *original_lines[original_target.end_lineno :],
        ]
    )
    target.body = original_target.body
    if updated != reconstructed or ast.dump(before) != ast.dump(after):
        raise ValueError("the applied patch changed code outside the selected function body")
    cases = [(arguments, oracle(*arguments)) for split in splits for arguments in split]
    if any(bounded.run(arguments).answer != expected for arguments, expected in cases):
        raise ValueError("applied function failed the bounded native-probe preflight")
    probe = reconstructed + (
        f"\nfor arguments, expected in {cases!r}:\n"
        f"    result = {function}(*arguments)\n"
        "    if type(result) is not int or result != expected:\n"
        "        raise AssertionError('synthetic Python regression')\n"
    )
    subprocess.run(
        [sys.executable, "-I", "-B", "-"],
        input=probe.encode("utf-8"),
        capture_output=True,
        timeout=15,
        check=True,
    )
    return len(cases)


def run(root, model, suite, attempts):
    hashes = json.loads((root / "inputs.json").read_text(encoding="utf-8"))
    for relative, expected in hashes.items():
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != expected:
            raise ValueError("prepared experiment inputs changed")
    summary = []
    for project, (function, code, description, oracle, *splits) in projects(suite).items():
        directory = root / project
        report_path = directory / "report.json"
        patch = directory / "candidate.diff"
        project_dir = directory / "project"
        original = (project_dir / "src" / f"{project}.py").read_text(encoding="utf-8")
        if original != synthetic_source(project, code):
            raise ValueError("the native probe accepts only the bundled synthetic source")
        cmd = [
            sys.executable,
            "-m",
            "morph.cli",
            "repair",
            "--project",
            str(project_dir),
            "--source",
            f"src/{project}.py",
            "--function",
            function,
            "--description",
            description,
            "--model",
            model,
            "--attempts",
            str(attempts),
            "--development",
            str(directory / "development.json"),
            "--validation",
            str(directory / "validation.json"),
            "--holdout",
            str(directory / "holdout.json"),
            "--ledger",
            str(directory / "holdout.db"),
            "--report",
            str(report_path),
            "--patch",
            str(patch),
        ]
        outcome = subprocess.run(cmd, check=False)
        row = {"project": project, "exit_code": outcome.returncode}
        if outcome.returncode == 0:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            row.update(
                {
                    key: report[key]
                    for key in ("status", "generation", "model", "baseline_validation")
                }
            )
            for split in ("validation", "holdout"):
                if split in report:
                    row[split] = {
                        key: report[split][key]
                        for key in ("n", "baseline_success", "candidate_success", "regressions")
                    }
            if report["status"] == "eligible_for_review":
                patched = directory / "patched"
                shutil.copytree(project_dir, patched)
                command = ["git", "apply", "--no-index", str(patch.resolve())]
                subprocess.run([*command, "--check"], cwd=patched, check=True)
                subprocess.run(command, cwd=patched, check=True)
                src = patched / "src" / f"{project}.py"
                updated = src.read_text(encoding="utf-8")
                if updated == original or not updated.endswith("def status():\n    return 200\n"):
                    raise ValueError(
                        "patch did not change the target or changed an unrelated function"
                    )
                row["native_python_cases"] = native_check(
                    original, updated, function, oracle, splits
                )
                row["patch_applied_to_copy"] = True
        summary.append(row)
    with (root / "summary.json").open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=2)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    setup = sub.add_parser("prepare")
    setup.add_argument("directory", type=Path)
    setup.add_argument("--suite", choices=("initial", "followup"), default="followup")
    experiment = sub.add_parser("run")
    experiment.add_argument("directory", type=Path)
    experiment.add_argument("--model", default="qwen3:4b")
    experiment.add_argument("--suite", choices=("initial", "followup"), default="followup")
    experiment.add_argument("--attempts", type=int, choices=(1, 2), default=2)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.directory, args.suite)
    else:
        summary = run(args.directory, args.model, args.suite, args.attempts)
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
