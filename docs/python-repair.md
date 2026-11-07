# Repair a Python function with a local model

`morph repair` reads one top-level function from a Python project, reproduces a bug, asks a local Ollama model for a replacement, and verifies the replacement before exporting a Git patch. The original project files stay untouched during the run.

## Requirements

Follow the [installation guide](installation.md) and install the provider extra inside your virtual environment with `python -m pip install -e '.[openai]'`. Start an existing Ollama server bound to `127.0.0.1:11434` with cloud features disabled and a model already on disk. The example uses `qwen3:4b`. No model is downloaded by MORPH. [Ollama for Windows](https://docs.ollama.com/windows)

## Prepare the cases

Each split is a JSON array. Every row has a unique ID, positional integer arguments and the expected integer result. For example, one failing case for a function that should count partially filled boxes is:

```json
[
  {"id": "partially-filled-box", "values": [9, 4], "expected": 3}
]
```

- Development must reproduce at least one bug. The model receives the selected function, the optional description and failing development examples.
- Validation needs at least 20 distinct cases. Include edge cases and examples that already pass so the comparison can detect regressions.
- Holdout is optional. Supply a separate case file and a SQLite ledger together. Keep these cases out of the development description. The ledger reserves them before evaluation and refuses reuse in that database.

MORPH rejects overlapping IDs or argument lists across splits. Select a target with one to eight ordinary positional integer parameters. UTF-8 source files need a final newline. Use a forward-slash path relative to the project, such as `src/warehouse.py`. Paths with spaces or symlinks inside the project are outside the supported patch format.

## Run and review

Create a private output directory, for example `local-results/`. From your environment, run:

```sh
python -m morph.cli repair --project . --source src/warehouse.py --function box_count --description "Count boxes, rounding up when there are leftover items." --model qwen3:4b --development local-results/dev.json --validation local-results/val.json --holdout local-results/holdout.json --ledger local-results/holdout.db --report local-results/repair.json --patch local-results/repair.diff
```

The default allows up to two generation attempts. A second attempt is used only when the first candidate is invalid or fails development. It receives no validation or holdout data. Use `--attempts 1` for a single request. The first candidate that passes development must then keep the signature and pass validation and the optional holdout. Validation needs at least one improvement over the original function. The report records the outcome even when an invalid or unsuccessful candidate yields no diff.

Read the patch before applying it. From the project's root:

```sh
git apply --check local-results/repair.diff
git apply local-results/repair.diff
```

Run the project's own trusted tests after applying the reviewed patch. The CLI never applies a patch automatically. Reports and diffs can contain project source and should stay private.

## Reproduce the four-project experiment

```sh
python examples/python_repair.py prepare local-results/repair-study --suite followup
python examples/python_repair.py run local-results/repair-study --suite followup --model qwen3:4b --attempts 2
```

Create `local-results/` first. The preparation command generates four small synthetic projects, separate cases and input hashes. The run uses the normal CLI once per project and compares with the original function. It applies each exported diff to a scratch copy and runs the synthetic function in CPython after checking the surrounding source and the candidate's restricted syntax. Use `--suite initial` on both commands and `--attempts 1` on `run` to reproduce the earlier exploratory suite. Raw artifacts stay in the output directory. [Published aggregate results](../reports/README.md)

## Scope

The verifier reads Python source and interprets only the selected function's restricted syntax tree. It supports integer constants, assignments, arithmetic, comparisons, branches and returns. It rejects calls, loops, imports inside the function, decorators, default parameters and changes to the signature. It does not import the project, evaluate annotations or run a project's test commands. Module initialization, external dependencies and interactions with other functions remain outside this verifier.

The report is evidence for the supplied integer cases. A successful patch is ready for review and project testing.
