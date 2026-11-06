# Roadmap

## Available in the experimental preview

- Minimal agent/model contracts and synthetic arithmetic tasks.
- Bounded integer-language interpreter and explicit experimental Docker runtime.
- Development-only synthesis, paired validation and SQLite review metadata.
- Evidence-bound routing, rollback metadata and single-use holdout records.
- Local model measurement and documented negative exploratory results.

## Next: strengthen evaluation

- Separate provider failures from model-output and task failures.
- Pre-register splits, evaluation budgets and stopping rules.
- Compare retry, fixed-instruction, predefined-tool and generated-patch variants under comparable budgets.
- Add repeated trials and uncertainty estimates without tuning on final holdout.
- Review interpreter behavior and Docker cleanup on isolated infrastructure.

## Then: broaden the task contract

- User-supplied task specifications and verifiers with explicit privacy boundaries.
- External agents and coding tasks, rather than replacement arithmetic execution.
- Revisable failure diagnoses and better candidate provenance.
- Routing and negative-transfer evaluation across genuinely distinct task families.

## Research release criteria

A research release needs independent datasets, accepted model-generated capabilities, complete cost accounting, regression analysis, a frozen final evaluation and comparison to relevant alternatives. The current preview does not meet these criteria. Marketplace, cross-model transfer and long-term evolution remain research directions.
