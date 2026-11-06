"""Offline lifecycle fixture. No network, model calls, or autonomous-generation claim."""

import argparse
import json
from pathlib import Path

from morph.bounded import BoundedRunner
from morph.demo import MockAgent, synthesis_tasks
from morph.evolution import evolve


class FixtureGenerator:
    def complete(self, prompt: str) -> str:
        return json.dumps(
            {
                "hypothesis": "Preserve signs while adding input values (fixed offline fixture)",
                "code": "def solve(values):\n total = 0\n for value in values:\n  total += value\n return total",
            }
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="new private report file; no overwrite")
    args = parser.parse_args()
    if args.output and args.output.exists():
        raise FileExistsError(args.output)
    development, validation = synthesis_tasks()
    report = evolve(
        MockAgent(),
        FixtureGenerator(),
        BoundedRunner(),
        development,
        validation,
        "mock-absolute-sum-v1",
    )
    report["mode"] = "offline infrastructure fixture; fixed generator; no LLM improvement claim"
    text = json.dumps(report, indent=2)
    if args.output:
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(text)
    print(text)


if __name__ == "__main__":
    main()
