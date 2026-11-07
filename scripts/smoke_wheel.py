"""Install the wheel into a temporary clean environment and verify the offline path."""

import argparse
import json
import os
import subprocess
import tempfile
import venv
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    wheel = args.wheel.resolve(strict=True)
    scratch = Path(".tmp").resolve()
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="wheel-smoke-", dir=scratch) as directory:
        root = Path(directory).resolve()
        if not root.is_relative_to(scratch):
            raise RuntimeError("unexpected temporary environment path")
        venv.EnvBuilder(with_pip=True).create(root / "venv")
        executable = root / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in {"PYTHONPATH", "PYTHONHOME"}
        }
        subprocess.run(
            [str(executable), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)],
            cwd=root,
            env=env,
            check=True,
            capture_output=True,
        )
        help_result = subprocess.run(
            [str(executable), "-I", "-m", "morph.cli", "repair", "--help"],
            cwd=root,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        assert "--holdout" in help_result.stdout and "--patch" in help_result.stdout
        for command in ("demo", "benchmark"):
            run = subprocess.run(
                [str(executable), "-I", "-m", "morph.cli", command],
                cwd=root,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            report = json.loads(run.stdout)
            if command == "demo":
                assert report["comparison"]["status"] == "inconclusive"
                assert report["comparison"]["candidate_success"] == 1
            else:
                assert report["strategies"]["baseline"]["success_rate"] == 0.25
        subprocess.run(
            [
                str(executable),
                "-I",
                "-c",
                "from morph.bounded import BoundedRunner; assert BoundedRunner().run('def solve(values): return sum(values)', [5,-2]).answer == 3",
            ],
            cwd=root,
            env=env,
            check=True,
            capture_output=True,
        )
    print("Clean wheel installation and offline commands passed.")


if __name__ == "__main__":
    main()
