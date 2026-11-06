# Experimental results

These measurements describe the current preview, including failed attempts. They do not establish autonomous improvement or capability transfer. This public summary excludes raw local requests, responses, runtime logs and machine-specific records.

## Offline infrastructure checks

| Example | Baseline | Candidate | Meaning |
|---|---:|---:|---|
| Small mock demo | 1/4 | 4/4 | Fixed operation proposal; decision is `inconclusive` |
| Bounded evolution fixture | 20/40 | 40/40 | Fixed code fixture interpreted by the real bounded runner; eligible for explicit review |

These are synthetic deterministic fixtures, not LLM improvement results. Reproduce with `python -m morph.cli demo`, `python -m morph.cli benchmark` and `python examples/bounded_evolution.py` after [installation](../docs/installation.md).

## Exploratory local-model measurements

One fixed local Ollama 0.32.6 run used the already installed `qwen2.5-coder:7b`, model digest `dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364`. The bundled dataset contains 2 development and 40 distinct validation inputs, all signed addition. Both runs used temperature 0, seed 0, a 256-output-token limit and no request retries. The strict evaluator requires a JSON object with an integer `answer` field.

| Configuration | Development correct | Validation correct | Validation contract errors | Validation inference time |
|---|---:|---:|---:|---:|
| JSON-object mode | 0/2 | 0/40 | 40 missing required fields | 20.73 s |
| Predefined required-answer schema | 1/2 | 1/40 | 0 | 21.96 s |

The schema control eliminated output-contract errors in that run but left arithmetic failures. It was tried after inspecting development failures and the first aggregate validation outcome, so this is exploratory validation reuse, not an independent final test. One small run cannot characterize the model or establish a cause for the unexpectedly poor accuracy. Inference timing depends on the machine and includes no matched-cost comparison to generated tools.

Two local synthesis attempts used only the development failures. One returned invalid Python; another, using an installed `qwen3:4b` on CPU, exhausted a 1024-token output limit before completing valid JSON. Both were rejected before algorithm execution. No model-generated candidate was accepted or activated, and no final holdout was accessed.

The schema-control run reported GPU placement. A separate single-example native CPU diagnostic still violated the output contract; its API and runner settings differed, so it does not isolate the cause. Local API charges were zero; energy and hardware costs were not measured. Docker integration was not run for these measurements.

## Reproduction and evidence limits

The [experiment protocol](../docs/real-model-experiment.md) documents the commands, task generator, output contracts, sampling settings and stopping rules. The release includes the implementation and aggregate observations; raw local logs are not distributed. Independent replay is therefore required to audit the aggregates from public materials. Source snapshots were not archived for the first run, and fixed seed/temperature do not ensure bitwise replay across runtimes and hardware.

The bounded interpreter and lifecycle are covered by automated tests. Docker integration tests are opt-in and remain outside these results. Current [CI checks](https://github.com/meanywe54-hub/morph-ai/actions/workflows/ci.yml) report the release's actual test/build status; a passing software test is not evidence of generalization.
