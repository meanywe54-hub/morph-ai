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

Two earlier local synthesis attempts used only the development failures. One returned invalid Python. The other, using an installed `qwen3:4b` on CPU, reached a 1024-token output limit before completing valid JSON. Both were rejected before algorithm execution.

The schema-control run reported GPU placement. A separate single-example native CPU diagnostic still violated the output contract; its API and runner settings differed, so it does not isolate the cause. Local API charges were zero; energy and hardware costs were not measured. Docker integration was not run for these measurements.

## Local model generated a working signed-addition function

One code-only synthesis request to the installed `qwen3:4b` produced a loop that adds each signed integer to an accumulator. MORPH asked for the signed sum, supplied only failed development evidence, parsed the returned function and interpreted it with `bounded-integer-v1`. The candidate was eligible for review and evaluated unchanged on a separate holdout. Its status remains experimental and it was never activated.

| Split | Direct model correct | Generated function correct | Improvements | Regressions | Execution errors |
|---|---:|---:|---:|---:|---:|
| Validation (recorded schema-control baseline) | 1/40 | 40/40 | 39 | 0 | 0 |
| Holdout (fresh baseline, same model digest and answer schema) | 0/24 | 24/24 | 24 | 0 | 0 |

The generator used Ollama 0.32.6, model digest `359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`, CPU, a 4096-token context, thinking disabled, temperature 0, seed 0 and a 256-token output limit. The one request took 13.93 seconds including load and returned 40 output tokens from 221 input tokens. After synthesis, the candidate made zero model calls. The 24 direct holdout calls took 21.74 seconds in total, and the 24 interpreter executions took about 1.8 milliseconds. The timing sums exclude test harness overhead and reflect different execution mechanisms. Synthesis time is separate. All inference was local and hardware and energy costs were unpriced.

The 24 holdout inputs were generated before synthesis using seed 17041, lengths 3–8 and integer values from −900 to 900. MORPH checked exact input separation and reserved the split in a fresh SQLite ledger before evaluation. The canonical task digest was `2bf4a758ee929c7d32842750b235bbcfa49459554ebe83a07b84436ab274d679`. The holdout was evaluated once.

The code-only format was designed after earlier failed synthesis attempts, and validation reused the prior schema-control result. Holdout gives a fresh same-task comparison, with a small synthetic sample and a surprisingly weak direct-model baseline. The candidate implements the stated arithmetic operation, which a prewritten sum can also solve. This experiment measures whether MORPH can generate and verify one executable replacement. Broader task transfer, autonomous discovery and matched-budget superiority remain untested.

## Local Python project repair

MORPH received one faulty function at a time from small synthetic Python projects. Each project had a separate development, validation and holdout split. The baseline was the original function executed under the same interpreter on the same inputs. Each prompt included the intended behavior and only failed development examples. Validation and holdout were never sent to the model. The tests compare repairs with the original code and do not benchmark competing repair agents.

The initial single-attempt run exported patches for metering and billing. Warehouse and settlement failed development and yielded no patch. The two exported patches scored 48/48 on validation against 30/48 for the original functions, and 48/48 on holdout against 30/48. Both diffs applied to scratch copies. The failed projects' original functions scored 9/24 and 5/24 on validation. No candidate validation or holdout score was recorded for those two projects.

After the initial run, MORPH gained an optional second attempt using only development feedback. Four new synthetic projects and their case files were frozen before the follow-up run. All four yielded a patch on the first attempt, so these measurements do not estimate the benefit of the retry.

| Project | Original validation | Patched validation | Original holdout | Patched holdout |
|---|---:|---:|---:|---:|
| Inventory rounding | 1/24 | 24/24 | 7/24 | 24/24 |
| Payroll overtime | 12/24 | 24/24 | 12/24 | 24/24 |
| Shipping threshold | 16/24 | 24/24 | 18/24 | 24/24 |
| Signed accounting change | 0/24 | 24/24 | 0/24 | 24/24 |
| **Total** | **29/96** | **96/96** | **37/96** | **96/96** |

All four follow-up diffs applied to separate project copies. Each applied function passed the same 51 development, validation and holdout cases in CPython, for 204 native checks. Validation and holdout found zero regressions. The four synthesis requests took 30.88 seconds in total, including model load, with 713 input and 129 output tokens. Execution after synthesis made no model calls.

Both runs used local `qwen3:4b`, digest `359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`, on Ollama 0.32.6, with thinking disabled, temperature 0, seed 0 and a 320-token response limit. The input manifests were hashed before generation. The four-project results are measurements of narrow, explicitly described integer bugs. They provide no estimate for arbitrary Python projects, dependency failures, multiple-file bugs or repository-scale repair. [Reproduction commands and supported syntax](../docs/python-repair.md)

## Reproduction and evidence limits

The [experiment protocol](../docs/real-model-experiment.md) documents the commands, task generator, output contracts, sampling settings and stopping rules. The release includes the implementation and aggregate observations; raw local logs are not distributed. Independent replay is therefore required to audit the aggregates from public materials. Source snapshots were not archived for the first run, and fixed seed/temperature do not ensure bitwise replay across runtimes and hardware.

The bounded interpreter and lifecycle are covered by automated tests. Docker integration tests are opt-in and remain outside these results. Current [CI checks](https://github.com/meanywe54-hub/morph-ai/actions/workflows/ci.yml) report the release's actual test/build status; a passing software test is not evidence of generalization.
