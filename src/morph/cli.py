"""Command-line entry point."""

import argparse
import json
import sqlite3
from pathlib import Path

from morph.demo import run_demo
from morph.registry import save
from morph.sandbox import SandboxFailure, SandboxUnavailable


def main() -> None:
    parser = argparse.ArgumentParser(prog="morph")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="run the synthetic offline demonstration")
    demo.add_argument("--db", type=Path, help="optional SQLite experiment database")
    bench = sub.add_parser("benchmark", help="compare synthetic mock strategies")
    bench.add_argument("--db", type=Path, help="optional SQLite experiment database")
    local = sub.add_parser(
        "local-baseline", help="measure an installed Ollama model; no generated code execution"
    )
    local.add_argument("--model", required=True)
    local.add_argument("--output", type=Path, required=True)
    local.add_argument("--seed", type=int, default=0)
    local.add_argument("--max-tokens", type=int, default=256)
    local.add_argument(
        "--answer-schema", action="store_true", help="predefined structured-output control"
    )
    live = sub.add_parser(
        "synthesize", help="call an LLM and evaluate a candidate (may cost money)"
    )
    live.add_argument("--model", required=True, help="model name for the configured provider")
    live.add_argument(
        "--agent-model", help="optional real baseline model; incurs additional API calls"
    )
    live.add_argument(
        "--agent-input-per-million", type=float, help="baseline input USD per million tokens"
    )
    live.add_argument(
        "--agent-output-per-million", type=float, help="baseline output USD per million tokens"
    )
    live.add_argument("--base-url", help="optional OpenAI-compatible API base URL")
    live.add_argument("--input-per-million", type=float, help="input USD per million tokens")
    live.add_argument("--output-per-million", type=float, help="output USD per million tokens")
    live.add_argument("--image", default="python:3.12-slim", help="trusted locally available image")
    live.add_argument(
        "--runtime", choices=["docker-python", "bounded-integer-v1"], default="docker-python"
    )
    live.add_argument("--db", type=Path, help="optional SQLite experiment database")
    register = sub.add_parser("register", help="register a patch and its validation report")
    register.add_argument("--db", type=Path, required=True)
    register.add_argument("--report", type=Path, required=True)
    for command in ("activate", "rollback"):
        control = sub.add_parser(command, help=f"{command} a reviewed patch")
        control.add_argument("--db", type=Path, required=True)
        control.add_argument("--patch", required=command == "activate")
        control.add_argument("--reviewer", required=True)
        control.add_argument("--reason", required=True)
    router = sub.add_parser("route", help="recommend whether to use the active patch")
    router.add_argument("--db", type=Path, required=True)
    router.add_argument("--report", type=Path, required=True)
    router.add_argument("--category", required=True)
    router.add_argument("--max-cost-usd", type=float)
    router.add_argument("--max-elapsed-s", type=float)
    holdout = sub.add_parser("holdout", help="evaluate an approved patch once on a holdout file")
    holdout.add_argument("--db", type=Path, required=True)
    holdout.add_argument("--report", type=Path, required=True)
    holdout.add_argument("--tasks", type=Path, required=True)
    holdout.add_argument("--dataset-id", required=True)
    holdout.add_argument("--image", default="python:3.12-slim")
    holdout.add_argument("--base-url", help="same provider endpoint as the baseline experiment")
    holdout.add_argument("--agent-input-per-million", type=float)
    holdout.add_argument("--agent-output-per-million", type=float)
    args = parser.parse_args()
    if args.command == "local-baseline":
        from morph.local_baseline import run_ollama

        result = run_ollama(args.model, args.output, args.seed, args.max_tokens, args.answer_schema)
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "status": result["status"],
                    "splits": result["splits"],
                },
                indent=2,
            )
        )
        return
    if args.command in {"register", "activate", "rollback", "route", "holdout"}:
        from morph.registry import (
            activate,
            active_patch,
            matches_evidence,
            matches_provenance,
            register_patch,
            rollback,
        )
        from morph.router import route

        try:
            if args.command in {"register", "route", "holdout"}:
                source = json.loads(args.report.read_text(encoding="utf-8-sig"))
                if (
                    not isinstance(source, dict)
                    or not isinstance(source.get("patch"), dict)
                    or not isinstance(source.get("comparison"), dict)
                ):
                    raise ValueError("report must contain patch and comparison objects")
            if args.command == "register":
                comparison = source["comparison"]
                register_patch(
                    args.db,
                    source["patch"],
                    comparison["status"],
                    evidence=comparison,
                    provenance=source,
                )
                result = {"registered": source["patch"]["id"], "status": comparison["status"]}
            elif args.command == "activate":
                activate(args.db, args.patch, approved_by=args.reviewer, reason=args.reason)
                result = {"active_patch": active_patch(args.db)}
            elif args.command == "rollback":
                rollback(args.db, args.patch, approved_by=args.reviewer, reason=args.reason)
                result = {"active_patch": active_patch(args.db)}
            elif args.command == "route":
                result = route(
                    args.db,
                    args.category,
                    source,
                    max_cost_usd=args.max_cost_usd,
                    max_elapsed_s=args.max_elapsed_s,
                )
            else:
                from morph.demo import MockAgent, Patch
                from morph.evolution import PatchedAgent
                from morph.execution import runner_for
                from morph.holdout import evaluate_once, load_tasks
                from morph.patches import CodePatch

                patch = active_patch(args.db)
                if (
                    patch is None
                    or patch != source["patch"]
                    or not matches_evidence(args.db, patch["id"], source["comparison"])
                    or not matches_provenance(args.db, patch["id"], source)
                ):
                    raise ValueError("report does not match the active reviewed patch")
                source_agent = patch["source_agent"]
                if source_agent == "mock-absolute-sum-v1":
                    baseline = MockAgent()
                elif source_agent.startswith("openai:"):
                    from openai import OpenAI

                    from morph.agents import ModelAgent
                    from morph.providers import OpenAICompatibleModel

                    baseline = ModelAgent(
                        OpenAICompatibleModel(
                            OpenAI(base_url=args.base_url, max_retries=0, timeout=60),
                            source_agent[7:],
                            input_per_million=args.agent_input_per_million,
                            output_per_million=args.agent_output_per_million,
                        )
                    )
                else:
                    raise ValueError("unsupported baseline agent")
                if "code" in patch:
                    sandbox = runner_for(patch.get("runtime", "docker-python"), args.image)
                    sandbox.preflight()
                    candidate = PatchedAgent(CodePatch(**patch), sandbox)
                elif patch.get("operation") == "signed_sum":
                    candidate = MockAgent(Patch(patch["id"], "holdout", "signed_sum"))
                else:
                    raise ValueError("unsupported patch type")
                result = evaluate_once(
                    args.db,
                    args.dataset_id,
                    baseline,
                    candidate,
                    load_tasks(args.tasks, source),
                    metadata={"patch_id": patch["id"], "source_agent": source_agent},
                )
        except (
            OSError,
            ValueError,
            KeyError,
            sqlite3.Error,
            ImportError,
            SandboxUnavailable,
        ) as exc:
            parser.error(str(exc))
        print(json.dumps(result, indent=2))
        return
    if args.command == "demo":
        report = run_demo()
    elif args.command == "benchmark":
        from morph.benchmark import RetryAgent, benchmark
        from morph.demo import MockAgent, Patch, tasks

        _, validation = tasks()
        patch = Patch("predefined", "signed sum", "signed_sum")
        report = benchmark(
            {
                "baseline": MockAgent(),
                "retry_twice": RetryAgent(MockAgent()),
                "predefined_tool": MockAgent(patch),
                "mock_morph": MockAgent(patch),
            },
            validation,
            baseline_name="baseline",
        )
        report["mode"] = "synthetic mock comparison; predefined tool and mock MORPH are identical"
    else:
        from morph.demo import MockAgent, synthesis_tasks
        from morph.evolution import evolve
        from morph.execution import runner_for
        from morph.providers import OpenAICompatibleModel

        sandbox = runner_for(args.runtime, args.image)
        try:
            sandbox.preflight()
        except SandboxUnavailable as exc:
            parser.error(str(exc))
        try:
            from openai import OpenAI
        except ImportError as exc:
            parser.error("install the optional dependency: pip install '.[openai]'")
            raise AssertionError from exc
        client = OpenAI(base_url=args.base_url, max_retries=0, timeout=60)
        development, validation = synthesis_tasks()
        if args.agent_model:
            from morph.agents import ModelAgent

            baseline = ModelAgent(
                OpenAICompatibleModel(
                    client,
                    args.agent_model,
                    input_per_million=args.agent_input_per_million,
                    output_per_million=args.agent_output_per_million,
                )
            )
            source_agent = f"openai:{args.agent_model}"
        else:
            baseline = MockAgent()
            source_agent = "mock-absolute-sum-v1"
        try:
            report = evolve(
                baseline,
                OpenAICompatibleModel(
                    client,
                    args.model,
                    input_per_million=args.input_per_million,
                    output_per_million=args.output_per_million,
                ),
                sandbox,
                development,
                validation,
                source_agent,
            )
        except (ValueError, SandboxFailure) as exc:
            parser.error(str(exc))
        report["mode"] = f"LLM-generated code; synthetic tasks; runtime={args.runtime}"
    if args.db:
        report["experiment_id"] = save(args.db, report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
