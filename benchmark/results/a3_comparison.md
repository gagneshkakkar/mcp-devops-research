# Benchmark Comparison

Descriptive comparison of saved pilot runs on a custom 10-case dataset.

| Approach | Passed | Cases | Pass rate |
|---|---:|---:|---:|
| Rule-based baseline | 9 | 10 | 90.0% |
| Single LLM | 7 | 10 | 70.0% |
| LLM + semantic RAG | 7 | 10 | 70.0% |
| LLM + semantic RAG + MCP | 8 | 10 | 80.0% |
| LLM + leave-one-case-out semantic RAG | 7 | 10 | 70.0% |
| Proposed multi-agent repair pipeline | 9 | 10 | 90.0% |

## Instrumented Repeat Run: LLM + Semantic RAG

- Run ID: `27a8a352-368e-441c-9c12-00cca7ba979e`
- Source: `rag_instrumented_results.json`
- Started (UTC): `2026-10-16T07:47:18.920265+00:00`
- Completed (UTC): `2026-10-16T07:54:43.527743+00:00`
- Model: `qwen2.5-coder:7b`
- Embedding model: `nomic-embed-text`
- Top K: 3
- Passed: 7/10
- Pass rate: 70.0%
- Total elapsed time: 444.6072 seconds

### Aggregate token usage

- prompt_tokens: 6528
- completion_tokens: 371
- total_tokens: 6899

### Per-case timing and token usage

| Case | Status | Total (s) | Retrieval (s) | Generation (s) | Evaluation (s) | Total tokens |
|---|---|---:|---:|---:|---:|---:|
| F01 | passed | 111.645 | 35.9015 | 75.7261 | 0.005 | 717 |
| F02 | passed | 50.9273 | 5.5889 | 45.3206 | 0.0037 | 744 |
| F03 | passed | 41.9588 | 2.2653 | 39.6453 | 0.0352 | 678 |
| F04 | passed | 37.2335 | 2.3815 | 34.7466 | 0.0036 | 706 |
| F05 | passed | 28.3053 | 2.236 | 26.0389 | 0.019 | 651 |
| F06 | passed | 27.6138 | 2.2324 | 25.365 | 0.0054 | 642 |
| F07 | passed | 34.032 | 2.3426 | 31.6751 | 0.0034 | 714 |
| F08 | error | 43.3317 | 2.2581 | 40.2446 | None | 672 |
| F09 | test_failed | 36.7624 | 2.3553 | 34.3895 | 0.0039 | 725 |
| F10 | test_failed | 32.5315 | 2.4535 | 29.7053 | 0.0046 | 650 |

A separate instrumented repeat of the semantic RAG approach. It is reported as a repeat run, not as a new approach or an independent baseline.

Limitations of the instrumented run:

- The result is from one run on the custom 10-case dataset.
- The original RAG retrieval corpus allows target-case self-retrieval.
- Token usage depends on what the local model endpoint reports.
- Elapsed time depends on local hardware and system load.
- The observed pass rate does not establish statistical significance or generalization to unseen projects.

## Overall Comparison Limitations

- Each overall result is from a saved pilot run on a small custom dataset.
- The rule-based baseline uses benchmark-specific rules.
- The original RAG corpus contains target-case broken evidence, allowing self-retrieval.
- LOCO excludes the target case, but the remaining corpus is still drawn from the same 10-case benchmark.
- The MCP experiment measures the combined LLM + RAG + MCP setup; it does not isolate the causal contribution of MCP.
- The proposed-system figure comes from the saved evaluation snapshot.
- These single pilot runs do not establish statistical significance.
- The instrumented RAG run is a repeat measurement, not an additional independent approach.

## Targeted Follow-up: F10 Prompt Experiment

- Status: **passed**
- Case: F10
- When the variable is unset: `https://example.test/api`
- When the variable is set: `https://configured.example/api`

A targeted single-case follow-up, not a 10-case benchmark result. Its status must not be compared directly with the overall pass rates.

This targeted test is reported separately and is not included as an overall benchmark row.

### Rule-based baseline

Uses benchmark-specific hand-coded rules, not a general repair system.

### Single LLM

One local Qwen call per case; no retries or fallbacks.

### LLM + semantic RAG

Historical run. The retrieval corpus includes target-case broken metadata/source, allowing self-retrieval.

### LLM + semantic RAG + MCP

Single pilot run; two cases failed behavioral evaluation.

### LLM + leave-one-case-out semantic RAG

Excludes each target case from retrieval. The observed result comes from one 10-case run and does not establish statistical significance or generalization to unseen projects.

### Proposed multi-agent repair pipeline

Uses the saved proposed-system evaluation snapshot; no experiment was rerun to generate this comparison.
