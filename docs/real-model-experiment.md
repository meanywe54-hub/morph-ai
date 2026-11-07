# Real-model experiments

A local Ollama experiment generated a signed-addition function and evaluated it in the bounded interpreter on validation and a separate holdout. The [results](../reports/README.md) document the scores, earlier failed attempts and scope of the experiment.

The current implementation evaluates signed-integer addition only. The model-backed baseline is asked for one JSON answer per task. A synthesis model receives only development failures and proposes a `solve(values)` function. The candidate replaces the baseline calculation in the selected bounded or Docker runtime; it is not a tool used by the language-model agent. Comparing their scores therefore compares different mechanisms and execution budgets.

Before accessing a holdout, record the model and provider, endpoint, date, pricing assumptions, container image digest, task files and code version. Prepare independent tasks and select the candidate using validation only. The bundled development and 40 validation inputs are synthetic and structurally similar; they are suitable for exercising the workflow, not for demonstrating generalization. Prepare holdout data separately and do not use its results to revise the same experiment.

On an isolated host with a trusted Docker daemon and local image, first run the opt-in Docker checks from the README. Then configure provider credentials and run, for example:

```sh
morph synthesize --model SYNTHESIS_MODEL --agent-model BASELINE_MODEL --db experiments.db > report.json
```

Use `--base-url` for a compatible endpoint, and supply `--input-per-million` and `--output-per-million` for synthesis pricing if known. The baseline's rates are configured independently with `--agent-input-per-million` and `--agent-output-per-million`. Without both corresponding rates, cost is unknown. Up to 43 API calls can occur before retries by the caller, and a separate Docker container is started for each of 40 validation tasks. Check provider prices and obtain authorization before running.

Review and register the saved report, explicitly activate a candidate only if it is eligible and reviewed, then run a single holdout as described in [evaluation.md](evaluation.md). The registered JSON report must be preserved without edits for CLI holdout. The holdout records ID and input fingerprints before execution. Baseline provider model name is recorded, but exact provider endpoint and model revision are not verified. For a custom endpoint, pass the same `--base-url` for holdout. Holdout baseline rates are independent CLI inputs.

Report all task outcomes, failures, paired improvements and regressions, runtime, model calls, provider-reported tokens and cost estimates, sample size and uncertainty. Repeat across tasks and seeds where supported; the current CLI does not automate seeds, confidence intervals, or a matched-budget retry, prompt and tool baseline for real models. Use the Python `benchmark` API for adapters with compatible tasks, and clearly disclose any differences in calls, available tools, costs or time. Do not select using the final holdout or describe a small synthetic result as cross-domain capability transfer.

## Existing local runtime without Docker

Baseline measurement can use an existing local Ollama installation. This path does not require Docker:

```sh
morph local-baseline --model qwen2.5-coder:7b --output baseline.json --seed 0 --max-tokens 256
morph local-baseline --model qwen2.5-coder:7b --output schema-control.json --seed 0 --max-tokens 256 --answer-schema
```

These commands require an already running local server and a model already on disk. They do not start the server or download weights. Sampling settings are recorded, but runtime and hardware still affect repeatability. The output file is written incrementally and is not overwritten by a new run. The schema control is a predefined intervention, not autonomous executable-tool creation. No holdout is consumed, and no generated code is executed.

### Reproduce bounded synthesis and holdout

Install the project with `python -m pip install -e '.[openai]'` in a virtual environment. This reproduction uses an existing Ollama server bound to `127.0.0.1:11434` with `qwen3:4b` and `qwen2.5-coder:7b` already on disk. Use a local-only server for this run. These commands use loopback HTTP and generate synthetic arithmetic data. [Ollama on Windows](https://docs.ollama.com/windows) · [Ollama chat API](https://docs.ollama.com/api/chat)

Create `local-results/` and record the strict-schema baseline:

```sh
python -m morph.cli local-baseline --model qwen2.5-coder:7b --output local-results/schema-control.json --seed 0 --max-tokens 256 --answer-schema
```

Save and run this Python snippet to generate the holdout before requesting the patch:

```python
import json
from pathlib import Path
from random import Random

rng = Random(17041)
rows = []
for i in range(24):
    values = [rng.randint(-900, 900) for _ in range(3 + i % 6)]
    rows.append(
        dict(id=f"local-holdout-{i + 1:02}", category="signed", values=values, expected=sum(values))
    )
with Path("local-results/holdout-17041.json").open("x", encoding="utf-8") as stream:
    json.dump(rows, stream, indent=2)
```

Then make one synthesis attempt and let the validation gate decide whether to evaluate the holdout:

```sh
python examples/evolve_recorded_local.py --model qwen3:4b --code-only --baseline local-results/schema-control.json --holdout local-results/holdout-17041.json --ledger local-results/holdout-evolution.db --output local-results/bounded-code-only.json
```

`--code-only` requests a JSON object with a single code field. MORPH supplies a generic hypothesis label for the record. The example validates the patch syntax and interpreter contract, compares it with the recorded validation runs, and writes the validation report before any holdout evaluation. Holdout requires `eligible_for_review`, checks the recorded baseline model digest and Ollama version, and uses the same strict answer schema for fresh baseline calls. SQLite reserves the inputs before those calls. Use this ledger once per holdout and keep the output and database local. A rerun can produce different scores. Keep the candidate fixed after holdout access and report any failed attempts.

This example measures a candidate in isolation and does not register or activate it. The separate review and activation workflow is described in the [walkthrough](walkthrough.md).
