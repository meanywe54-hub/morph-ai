# Related work and experimental position

These are starting points for comparison, not a claim of novelty. Links refer to primary papers or the authors' reports. A full systematic review and direct experiments remain future work.

| Work | Mechanism and evidence | Relevance and limits for MORPH |
|---|---|---|
| [Darwin Gödel Machine](https://arxiv.org/abs/2505.22954) | Evolves agent code in an archive and evaluates coding performance. | Directly precedes agent code evolution; benchmark gains do not by themselves establish broad transfer. |
| [AlphaEvolve](https://storage.googleapis.com/deepmind-media/DeepMind.com/Blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/AlphaEvolve.pdf) | Uses model-generated code, evaluators and evolutionary search for algorithm discovery. | Requires meaningful evaluators; improvements on its evaluated problems do not validate MORPH. |
| [GEPA](https://arxiv.org/abs/2507.19457) | Uses reflection on trajectories and evolutionary selection to optimize prompts. | A relevant baseline for instruction optimization; not equivalent to validated executable capabilities. |
| [Reflexion](https://arxiv.org/abs/2303.11366) | Uses verbal feedback and memory across trials. | Compare against retries with feedback; verbal reflection alone need not create a new tool. |
| [Voyager](https://arxiv.org/abs/2305.16291) | Accumulates executable skills in a Minecraft environment with iterative feedback. | Skill reuse is established prior work; environment-specific results do not guarantee cross-domain transfer. |
| [DSPy](https://arxiv.org/abs/2310.03714) | Optimizes declarative language-model programs against examples and metrics. | A practical optimization baseline; requires comparable budgets and independently held-out evaluation. |
| [SkillGen](https://arxiv.org/abs/2605.10999) | Evaluates generated agent skills as interventions and reports held-out and cross-model results. | An especially relevant prior comparator for the proposed transfer gate. |
| [Skill evaluation survey](https://arxiv.org/abs/2606.11435) | Surveys skill evolution and evaluation benchmarks. | Highlights the need to examine the whole skill lifecycle and generalization. |
| [SWE-bench](https://arxiv.org/abs/2310.06770) | Evaluates fixes for real software issues through tests. | A possible later benchmark; tests and public issue data have limitations and do not alone prove generalization. |

Candidate research question: under fixed budgets, does validation-based routing reduce negative transfer compared with always applying a patch, a retry baseline, and a prompt optimizer? Pre-register datasets and decision rules, keep final holdout access separate from selection, report uncertainty, costs and all regressions, and repeat across models and task families. The current mock cannot answer this question.
