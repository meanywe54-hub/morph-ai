# Walkthrough

Run commands with the virtual environment's Python. On Windows this can be ` .\.venv\Scripts\python.exe`; on Linux/macOS use `.venv/bin/python`. No activation or system configuration change is required.

## 1. Inspect the offline mock

```sh
python -m morph.cli demo
python -m morph.cli benchmark
```

The small demo prints a diagnosis, fixed operation proposal and paired outcomes: baseline 1/4, candidate 4/4, status `inconclusive`. The benchmark compares the mock baseline, two unconditional attempts, a predefined tool and a mock MORPH variant. The last two use the same operation. These examples verify the harness, not model improvement.

## 2. Interpret an executable algorithm

Create a private output directory (`mkdir local-results`), then run:

```sh
python examples/bounded_evolution.py --output local-results/candidate.json
```

The fixed fixture generator supplies a loop-based `solve(values)` function. The bounded runtime validates its syntax and interprets it on 40 separate synthetic validation inputs. Expected outcomes are baseline 20/40, candidate 40/40 and `eligible_for_review`. The generator is hard-coded, so this is not autonomous tool creation. The script performs no activation and accesses no final holdout.

## 3. Register evidence and review

```sh
python -m morph.cli register --db local-results/experiments.db --report local-results/candidate.json
```

Read `patch.id` from the report and replace `PATCH_ID` below. In PowerShell you can inspect `(Get-Content local-results/candidate.json -Raw | ConvertFrom-Json).patch.id`.

```sh
python -m morph.cli activate --db local-results/experiments.db --patch PATCH_ID --reviewer YOUR_NAME --reason 'Reviewed offline fixture'
python -m morph.cli route --db local-results/experiments.db --report local-results/candidate.json --category ledger
python -m morph.cli rollback --db local-results/experiments.db --reviewer YOUR_NAME --reason 'Disable fixture'
```

Activation is metadata only; it does not install code into a production agent. Review is a caller-supplied name and reason, not authentication. Routing gives a recommendation from the active version's recorded category evidence. Unknown costs are refused when a cost budget is set. Rollback without `--patch` disables the active patch; with an ID it restores a previously active version.

## 4. Final holdout

Choose the final candidate before opening holdout data. For a toy infrastructure check, a UTF-8 JSON file can contain:

```json
[{"id":"h1","category":"arithmetic","values":[1000,-7,2],"expected":995}]
```

After explicitly reactivating the fixture, run:

```sh
python -m morph.cli holdout --db local-results/experiments.db --report local-results/candidate.json --tasks local-results/holdout.json --dataset-id toy-final-1
```

The command verifies the active patch and full report, rejects exact development/validation overlap, then reserves the dataset and individual inputs before evaluating. Repeating that evaluation is refused in the same registry. One toy example is not evidence of generalization. Never use a final holdout to revise the same candidate.

## 5. Replace the fixture with a model

Install the optional SDK. A model command sends supplied task evidence to its provider and may incur charges:

```sh
python -m pip install -e '.[openai]'
python -m morph.cli synthesize --model MODEL --runtime bounded-integer-v1 --db local-results/experiments.db
```

Configure credentials in the current process as required by the provider; never commit them. The default baseline is still the mock. `--agent-model MODEL` adds real baseline calls on the narrow arithmetic tasks. `--base-url` chooses a compatible endpoint. The Docker runtime is selected with `--runtime docker-python` and requires an independently prepared trusted environment; it never falls back to host execution.

For local-only measurement, see [the experiment guide](real-model-experiment.md). For API details and decision limits, see [evaluation.md](evaluation.md). For rejected/inconclusive candidates, inspect errors and sample size rather than changing the evaluator to force a better score.
