# Baseline Comparison Report

Generated (UTC): 2026-10-15T08:48:53.029264+00:00

## Experiment Summary

| Approach | Passed | Unsupported | Errors | Test failed | Pass rate |
|---|---:|---:|---:|---:|---:|
| Rule-based baseline | 9/10 | 1 | 0 | 0 | 90.0% |
| Single-LLM baseline | 7/10 | 0 | 2 | 1 | 70.0% |
| Proposed multi-agent system | 9/10 | 1 | 0 | 0 | 90.0% |

## Interpretation

- The rule-based baseline achieved an observed 90% pass rate.
- The single-LLM baseline achieved an observed 70% pass rate.
- The proposed multi-agent system achieved an observed 90% pass rate.
- The rule-based baseline uses benchmark-specific deterministic rules.
- The single-LLM baseline uses one direct model call per case, without multi-agent orchestration or repair retries.
- The proposed-system figure comes from its saved evaluation report.

## Important Limitations

- The benchmark contains only ten cases.
- The rule-based rules are tailored to this benchmark and should not be treated as a general-purpose repair system.
- The results are observed outcomes from saved runs, not averages over repeated trials.
- The three approaches have different repair capabilities and failure handling, so pass rate alone does not explain their behavior.
- The proposed-system result is taken from the saved evaluation report; no new repair experiment was run.
- These results do not establish statistical significance or generalization to real-world CI failures.

## Source Files

- `baseline_rule_results.json`
- `baseline_single_llm_results.json`
- `evaluation_report.json`
