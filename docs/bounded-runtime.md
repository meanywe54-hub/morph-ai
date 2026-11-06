# Bounded integer runtime

`bounded-integer-v1` is a small algorithm language using Python syntax. MORPH walks the syntax tree with its own interpreter. It never compiles or executes that source as Python. This allows experiments on hosts where Docker is unavailable and installing system components is undesirable.

The language accepts exactly one `solve(values)` function. Its input is an immutable sequence of at most 1000 integers, each with magnitude at most one billion; its output must be an integer. It supports assignments, `if`, finite `for` loops over the input sequence, `return`, integer comparisons and arithmetic `+`, `-`, `*`, `//`, `%`. Trusted primitives `sum`, `len`, `abs`, `min`, and `max` accept one argument. The default execution budget is 20,000 interpreter steps, with at most 64 variables and integer magnitudes bounded by one trillion. Syntax is bounded to 100 KB, 2048 AST nodes and depth 32. A budget violation rejects the candidate.

Imports, attributes, indexing, mutation of input elements, strings, file/network access, general function calls, recursion, comprehensions, `while`, decorators and unknown statements are rejected, including unsupported syntax in unreachable branches. An optional input annotation must be `list[int]` and an optional return annotation must be `int`; annotations are checked as syntax and never evaluated. This restricted interpreter does not run arbitrary Python and provides no compatibility guarantee for general Python programs. Bugs in the trusted interpreter remain possible and require review.

Select it explicitly for synthesis:

```sh
morph synthesize --model MODEL --runtime bounded-integer-v1 --db experiments.db
```

The configured provider can incur charges; the bounded interpreter itself makes no provider calls. `--base-url` and the provider's usual credentials select the endpoint for this generic command. The runtime contract is included in the synthesis prompt and recorded in the candidate. Runtime identity is part of the patch fingerprint, so switching runtime after evaluation invalidates its evidence. Holdout CLI automatically selects the runtime stored in an approved patch. Earlier code-patch reports whose fingerprint did not include a runtime need fresh evaluation before registration.

For an installed local Ollama model, `examples/evolve_recorded_local.py` makes one native API synthesis request from development observations in a saved baseline and evaluates the candidate using the bounded runtime. It records the generator request/response and identity, the baseline hash, and paired validation outcomes. This is a comparison to frozen historical agent executions, not a fresh concurrent or matched-cost experiment. It performs no activation and uses no final holdout. The bundled tasks all involve signed addition; their category labels are not evidence of cross-domain transfer.
