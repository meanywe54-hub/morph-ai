# Proposed real-model experiment

The full model-generated-code experiment has **not run**. Local baseline measurements are available under [reports/](../reports/); these do not establish agent improvement or transfer.

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

`examples/propose_local_patch.py` can send only development observations from a completed baseline to the local model and save a generated candidate. Its JSON-schema response contract does not guarantee valid Python or useful behavior. Invalid Python is rejected by the existing synthesizer. A valid candidate remains pending isolated evaluation until suitable infrastructure is available.
