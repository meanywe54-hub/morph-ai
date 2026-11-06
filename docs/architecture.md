# Architecture

The preview is a single Python package with a dependency-free core. The OpenAI SDK and HTTP transport are optional. SQLite provides local persistence; the package does not start a web service.

| Module | Responsibility |
|---|---|
| `core.py` | Task, execution result and agent protocol |
| `agents.py`, `providers.py` | Arithmetic model adapter and optional provider interface |
| `experiment.py` | Observations, simple diagnosis and paired validation gate |
| `patches.py` | Development-only synthesis, patch representation and identity |
| `bounded.py`, `sandbox.py`, `execution.py` | Restricted interpreter, optional Docker runner and runtime selection |
| `evolution.py` | Connect development execution, synthesis and candidate evaluation |
| `registry.py` | Evidence validation, registration and activation/rollback events |
| `router.py` | Recommendations from active versions, matching evidence and budgets |
| `holdout.py` | Data loading, overlap checks and transactional one-use reservation |
| `benchmark.py`, `local_baseline.py` | Strategy comparison and local model measurement |

## Lifecycle and decisions

The engine runs development tasks and gives only their failures to a synthesizer. The result contains a hypothesis, code and source-agent identity. A runtime contract can constrain what is generated. Baseline and candidate results are then paired on validation inputs.

The gate rejects observed regressions and returns `inconclusive` when evidence is too small, lacks distinct inputs, has execution errors or shows no gain. Passing it yields `eligible_for_review`, not automatic activation or statistical significance.

Registration recalculates outcomes and binds evidence to the patch/runtime fingerprint. Reviewer metadata controls the active version. Routing checks matching evidence, sufficient distinct category inputs, improvement, absence of observed regressions and any historical cost/time limits.

Holdout is reserved before evaluation. Reusing its ID or an earlier holdout input is refused in the same database. CLI holdout also checks recorded development/validation overlap and the registered full report. This cannot detect paraphrases, out-of-band access, copied databases or intentional record edits.

## Current task contract

The bundled model agent adds signed integers and returns a JSON answer. A code patch replaces that calculation. MORPH does not yet modify the planning/tool workflow of an arbitrary software-engineering agent. A future task/verifier contract must preserve these evaluation and privacy boundaries.
