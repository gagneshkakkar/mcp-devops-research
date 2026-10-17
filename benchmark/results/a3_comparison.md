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

## Repeated-Run Statistics

Three repetitions per approach on the same 10-case benchmark.

| Approach | Runs | Mean pass rate | Pass-rate SD (pp) | Mean elapsed seconds | Elapsed SD (s) | Mean tokens |
|---|---:|---:|---:|---:|---:|---:|
| Rule-based | 3 | 90.0% | 0.0 | 0.115221 | 0.059158 | N/A |
| Single LLM | 3 | 70.0% | 0.0 | 138.099718 | 41.878103 | 2413 |
| LLM + Semantic RAG | 3 | 70.0% | 0.0 | 188.354994 | 63.358322 | 6024 |
| Proposed multi-agent repair pipeline | 3 | 90.0% | 0.0 | 710.4594326666667 | 13.407749422761793 | N/A |

### Additional latency metrics

| Approach | Metric | Mean seconds | Median seconds | SD (s) |
|---|---|---:|---:|---:|
| Single LLM | Generation | 137.936383 | 114.183589 | 41.80082 |
| LLM + Semantic RAG | Generation | 139.469698 | 105.596437 | 59.380995 |
| LLM + Semantic RAG | Retrieval | 48.637129 | 46.433148 | 3.843164 |

### Per-case outcome consistency

| Approach | Case | Observed outcomes across runs |
|---|---|---|
| Rule-based | F01 | passed: 3 |
| Rule-based | F02 | passed: 3 |
| Rule-based | F03 | passed: 3 |
| Rule-based | F04 | passed: 3 |
| Rule-based | F05 | passed: 3 |
| Rule-based | F06 | unsupported_syntax_error: 3 |
| Rule-based | F07 | passed: 3 |
| Rule-based | F08 | passed: 3 |
| Rule-based | F09 | passed: 3 |
| Rule-based | F10 | passed: 3 |
| Single LLM | F01 | passed: 3 |
| Single LLM | F02 | passed: 3 |
| Single LLM | F03 | passed: 3 |
| Single LLM | F04 | passed: 3 |
| Single LLM | F05 | passed: 3 |
| Single LLM | F06 | passed: 3 |
| Single LLM | F07 | passed: 3 |
| Single LLM | F08 | error: 3 |
| Single LLM | F09 | test_failed: 3 |
| Single LLM | F10 | error: 3 |
| LLM + Semantic RAG | F01 | passed: 3 |
| LLM + Semantic RAG | F02 | passed: 3 |
| LLM + Semantic RAG | F03 | passed: 3 |
| LLM + Semantic RAG | F04 | passed: 3 |
| LLM + Semantic RAG | F05 | passed: 3 |
| LLM + Semantic RAG | F06 | passed: 3 |
| LLM + Semantic RAG | F07 | passed: 3 |
| LLM + Semantic RAG | F08 | error: 3 |
| LLM + Semantic RAG | F09 | test_failed: 3 |
| LLM + Semantic RAG | F10 | test_failed: 3 |
| Proposed multi-agent repair pipeline | F01 | passed: 3 |
| Proposed multi-agent repair pipeline | F02 | passed: 3 |
| Proposed multi-agent repair pipeline | F03 | passed: 3 |
| Proposed multi-agent repair pipeline | F04 | passed: 3 |
| Proposed multi-agent repair pipeline | F05 | passed: 3 |
| Proposed multi-agent repair pipeline | F06 | unsupported_syntax_error: 3 |
| Proposed multi-agent repair pipeline | F07 | passed: 3 |
| Proposed multi-agent repair pipeline | F08 | passed: 3 |
| Proposed multi-agent repair pipeline | F09 | passed: 3 |
| Proposed multi-agent repair pipeline | F10 | passed: 3 |

### Repeated-run interpretation

These statistics summarize three repetitions of each approach on the same custom 10-case benchmark. They describe observed repeatability on this dataset and do not establish generalization or statistical significance.

Limitations:

- Only three repetitions per approach are included.
- The same custom 10-case benchmark and local machine are used.
- Repeated runs are not independent hardware trials.
- Pass-rate standard deviation describes variation across three observed run-level pass rates.
- Timing values are sums of per-case measurements, not full process wall-clock time.
- Rule-based timing excludes process startup and is not directly comparable to LLM generation latency alone.
- RAG corpus loading is reported separately from per-case retrieval and elapsed time.
- The RAG corpus is not an unseen-project test set.
- Token counts depend on the local endpoint's usage reporting.
- Token usage was not exposed by the proposed repair pipeline and is reported as unavailable, not zero.

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

A separate instrumented run of the semantic RAG approach. It is reported as a repeat run, not as a new approach or an independent baseline.

Limitations of the instrumented run:

- The result is from one run on the custom 10-case dataset.
- The original RAG retrieval corpus allows target-case self-retrieval.
- Token usage depends on what the local model endpoint reports.
- Elapsed time depends on local hardware and system load.
- The observed pass rate does not establish statistical significance or generalization to unseen projects.

## Overall Comparison Limitations

- The benchmark contains 10 custom cases.
- The rule-based baseline uses benchmark-specific rules.
- The original RAG corpus contains target-case broken evidence, allowing self-retrieval.
- LOCO excludes the target case, but the remaining corpus comes from the same benchmark.
- The MCP experiment measures the combined LLM + RAG + MCP setup; it does not isolate MCP's causal contribution.
- The overall proposed-system comparison row retains the saved evaluation snapshot; its three-run repeatability statistics are reported separately.
- Proposed-system token usage is unavailable because the current repair pipeline does not expose token counts; unavailable values are not treated as zero.
- Historical single-run results and repeated-run summaries are reported separately.
- Three repetitions do not establish statistical significance or generalization to unseen projects.

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

Excludes each target case from retrieval. The remaining corpus is still drawn from the same 10-case benchmark.

### Proposed multi-agent repair pipeline

Uses the saved proposed-system evaluation snapshot; no experiment was rerun to generate this comparison.
