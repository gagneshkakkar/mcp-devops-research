# CI/CD Autonomous Repair Evaluation Report

- **Experiment:** autonomous_ci_repair_benchmark
- **Source snapshot:** `repair_results_90pct_run.json`
- **Generated (UTC):** 2026-10-15T08:35:45.838703+00:00
- **Total cases:** 10
- **Passed:** 9
- **Unsupported:** 1
- **Failed/rejected:** 0
- **Observed pass rate:** 90.0%

## Repair strategy classifications

| Classification | Cases |
|---|---:|
| llm_patch_pipeline | 7 |
| llm_plus_dependency_cleanup | 1 |
| fallback_assisted | 1 |
| unsupported | 1 |
| other_or_unknown | 0 |

## Per-case results

| ID | Case | Status | Recorded strategy | Classification |
|---|---|---|---|---|
| F01 | Incorrect Arithmetic Logic | passed | llm_function_patch | llm_patch_pipeline |
| F02 | Incorrect Division Logic | passed | llm_function_patch | llm_patch_pipeline |
| F03 | Undefined Variable | passed | llm_function_patch | llm_patch_pipeline |
| F04 | Wrong Function Name | passed | llm_function_patch | llm_patch_pipeline |
| F05 | Missing Import | passed | missing_import_fallback | fallback_assisted |
| F06 | Syntax Error | unsupported_syntax_error | llm_function_patch | unsupported |
| F07 | Failed Assertion | passed | llm_function_patch | llm_patch_pipeline |
| F08 | Missing Dependency | passed | llm_function_patch | llm_plus_dependency_cleanup |
| F09 | Python Runtime Compatibility | passed | llm_function_patch | llm_patch_pipeline |
| F10 | Missing Environment Variable | passed | llm_function_patch | llm_patch_pipeline |

## Limitations

- This is one run on a custom benchmark of ten cases.
- The observed pass rate does not establish general repair reliability.
- F06 is unsupported by the current syntax-dependent repair pipeline.
- F05 uses a missing-import fallback.
- F08 uses an LLM patch followed by dependency cleanup.
- Strategy counts describe this run and are not baseline comparisons.

## Interpretation

The observed pass rate is descriptive of this specific run. It must not be interpreted as a general reliability estimate or as evidence of improvement over a baseline. Baseline and ablation experiments are required for those comparisons.
