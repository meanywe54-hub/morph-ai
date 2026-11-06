# Experimental evaluation APIs

`morph.benchmark.benchmark` evaluates named adapters on the same validation tasks. `RetryAgent` always takes a fixed number of attempts and returns the last one; it has no oracle or feedback. Compare agents with an explicitly recorded budget: retry costs more calls than a single attempt, so raw success rates alone are not a matched-budget comparison.

`evolve` generates a patch from development observations and compares it on validation tasks. Its `comparison` is eligible for review only under the current operational rule: at least 20 distinct inputs, at least one improvement, no regressions, and no execution errors. This is not statistical evidence of transfer; different inputs can still be highly correlated. The rule does not account for cost or latency in candidate selection.

For an eligible result, an application may register it with `register_patch(db, report["patch"], report["comparison"]["status"], evidence=report["comparison"])`. The registry checks the paired outcomes and binds the evidence to the patch ID and code fingerprint. A human can call `activate(db, patch_id, approved_by="...", reason="...")`; `rollback(db, previous_id, approved_by="...", reason="...")` restores a version that was active before, or `None` disables the active patch. These calls update metadata only and do not execute or install code.

`route(db, category, report, ...)` recommends the active patch only if the supplied report matches its recorded evidence, the category has enough distinct validation inputs, improves over baseline with no observed regressions, and meets any specified cost and latency budgets. Unknown costs or latency cause rejection when their budget is specified. These are historical averages, not guarantees about future tasks. There is no trained router.

The CLI exposes the same metadata operations. For example, after saving a synthesis report as `report.json`:

```sh
morph register --db experiments.db --report report.json
morph activate --db experiments.db --patch PATCH_ID --reviewer PERSON --reason 'Reviewed evidence'
morph route --db experiments.db --report report.json --category arithmetic
morph rollback --db experiments.db --reviewer PERSON --reason 'Disable patch'
```

An inconclusive or rejected patch cannot be activated. The offline demo's four validation tasks therefore cannot pass the current review threshold. The synthesis command uses 40 distinct but closely related synthetic validation inputs, which exercise the gate but do not establish independent generalization. A Docker candidate uses a separate container per task; a bounded candidate uses a fresh interpreter state per task. The reviewer field records a caller-supplied name; it does not authenticate the reviewer. A hash binds the recorded patch contents to the report but does not attest to the origin of the results or prevent a database owner from editing records.

`evaluate_once(db, dataset_id, baseline, candidate, tasks)` reserves a holdout ID and individual input fingerprints in SQLite before evaluating. Reuse of either the ID or any input from an earlier holdout is rejected in the same database, even if a run is interrupted. An older registry containing holdout records without input fingerprints is refused because prior use cannot be verified. The function reports outcomes without selecting a patch. The caller must choose the final candidate before opening the holdout and keep datasets separate; the API cannot detect paraphrases, leakage into development, a copied or reset database, or out-of-band access. A failed or interrupted holdout should not be rerun as if it were untouched.

The CLI runs holdout only for an active patch whose report matches the full report registered with `morph register`. Registrations made directly through Python need `provenance=report` in addition to `evidence=report["comparison"]` for CLI holdout:

```sh
morph holdout --db experiments.db --report report.json --tasks holdout.json --dataset-id final-2026
```

The task file must be a JSON array, for example `[{"id":"h1","category":"arithmetic","values":[100,-3],"expected":97}]`. The report must include recorded development inputs and validation results. Exact overlap with either earlier split is rejected before the holdout is reserved. For a model baseline, the saved model name is reused; if synthesis used `--base-url`, pass the same endpoint again. Endpoint identity and model version are not independently verified. This command can make paid model calls and uses the runtime recorded in the patch. Holdout inputs and results can be inspected by the operator; this workflow is not a secure blind evaluation.

Model token prices are supplied by the caller in USD per million tokens via `--input-per-million` and `--output-per-million` or `OpenAICompatibleModel`. When the response omits token counts or either rate is unknown, the cost is unknown. Estimates ignore provider-specific pricing details and are not billing records.
