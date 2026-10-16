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

## Limitations

- Each overall result is from a saved pilot run on a small custom dataset.
- The rule-based baseline uses benchmark-specific rules.
- The original RAG corpus contains target-case broken evidence, allowing self-retrieval.
- LOCO excludes the target case, but the remaining corpus is still drawn from the same 10-case benchmark.
- A3 measures the combined LLM + RAG + MCP setup; it does not isolate the causal contribution of MCP.
- The proposed-system figure comes from the saved evaluation snapshot.
- These single pilot runs do not establish statistical significance.

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

The retrieval corpus includes target-case broken metadata/source, allowing self-retrieval.

### LLM + semantic RAG + MCP

Single pilot run; two cases failed behavioral evaluation.

### LLM + leave-one-case-out semantic RAG

Excludes each target case from retrieval. The observed result comes from one 10-case run and does not establish statistical significance or generalization to unseen projects.

### Proposed multi-agent repair pipeline

Uses the saved proposed-system evaluation snapshot; no experiment was rerun to generate this comparison.
