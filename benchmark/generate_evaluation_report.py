
import json
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_FILE = (
    PROJECT_ROOT
    / "benchmark"
    / "results"
    / "repair_results_90pct_run.json"
)
REPORT_JSON = (
    PROJECT_ROOT / "benchmark" / "results" / "evaluation_report.json"
)
REPORT_MD = (
    PROJECT_ROOT / "benchmark" / "results" / "evaluation_report.md"
)


def load_results():
    if not RESULTS_FILE.is_file():
        raise FileNotFoundError(
            f"Results snapshot not found: {RESULTS_FILE}"
        )

    with RESULTS_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)

    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Results file has no valid cases list.")

    ids = [case.get("id") for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate case IDs found in results.")

    return data


def classify_strategy(case):
    """Classify the recorded strategy without inferring unrecorded behavior."""
    strategy = case.get("repair_strategy", "unknown")
    case_id = case.get("id")

    if case.get("status") == "unsupported_syntax_error":
        return "unsupported"

    if strategy == "missing_import_fallback":
        return "fallback_assisted"

    if strategy in {
        "targeted_ast_runtime_fallback",
        "targeted_runtime_fallback",
    }:
        return "fallback_assisted"

    # F08 uses an LLM patch followed by dependency cleanup.
    if case_id == "F08" and case.get("dependency_cleanup"):
        return "llm_plus_dependency_cleanup"

    if strategy == "llm_function_patch":
        return "llm_patch_pipeline"

    return "other_or_unknown"


def build_report(data):
    cases = data["cases"]
    total = len(cases)
    passed = sum(case.get("status") == "passed" for case in cases)
    unsupported = sum(
        case.get("status") == "unsupported_syntax_error"
        for case in cases
    )
    failed_or_rejected = total - passed - unsupported

    categories = {
        "llm_patch_pipeline": 0,
        "llm_plus_dependency_cleanup": 0,
        "fallback_assisted": 0,
        "unsupported": 0,
        "other_or_unknown": 0,
    }

    case_rows = []

    for case in cases:
        classification = classify_strategy(case)
        categories[classification] += 1

        case_rows.append({
            "id": case.get("id"),
            "title": case.get("title"),
            "status": case.get("status"),
            "recorded_strategy": case.get("repair_strategy", "unknown"),
            "classification": classification,
            "tests_passed": bool(case.get("tests_passed", False)),
        })

    return {
        "report_type": "isolated_ci_repair_benchmark",
        "source_file": str(RESULTS_FILE),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": data.get("experiment"),
        "mode": data.get("mode"),
        "total_cases": total,
        "passed_cases": passed,
        "unsupported_cases": unsupported,
        "failed_or_rejected_cases": failed_or_rejected,
        "observed_pass_rate_percent": round(
            100 * passed / total, 2
        ) if total else 0.0,
        "strategy_counts": categories,
        "cases": case_rows,
        "limitations": [
            "This is one run on a custom benchmark of ten cases.",
            "The observed pass rate does not establish general repair reliability.",
            "F06 is unsupported by the current syntax-dependent repair pipeline.",
            "F05 uses a missing-import fallback.",
            "F08 uses an LLM patch followed by dependency cleanup.",
            "Strategy counts describe this run and are not baseline comparisons.",
        ],
    }


def write_markdown(report):
    lines = [
        "# CI/CD Autonomous Repair Evaluation Report",
        "",
        f"- **Experiment:** {report.get('experiment')}",
        f"- **Source snapshot:** `{Path(report['source_file']).name}`",
        f"- **Generated (UTC):** {report['generated_at_utc']}",
        f"- **Total cases:** {report['total_cases']}",
        f"- **Passed:** {report['passed_cases']}",
        f"- **Unsupported:** {report['unsupported_cases']}",
        f"- **Failed/rejected:** {report['failed_or_rejected_cases']}",
        f"- **Observed pass rate:** {report['observed_pass_rate_percent']}%",
        "",
        "## Repair strategy classifications",
        "",
        "| Classification | Cases |",
        "|---|---:|",
    ]

    for name, count in report["strategy_counts"].items():
        lines.append(f"| {name} | {count} |")

    lines.extend([
        "",
        "## Per-case results",
        "",
        "| ID | Case | Status | Recorded strategy | Classification |",
        "|---|---|---|---|---|",
    ])

    for case in report["cases"]:
        title = str(case["title"]).replace("|", "\\|")
        lines.append(
            f"| {case['id']} | {title} | {case['status']} "
            f"| {case['recorded_strategy']} | {case['classification']} |"
        )

    lines.extend(["", "## Limitations", ""])
    for limitation in report["limitations"]:
        lines.append(f"- {limitation}")

    lines.extend([
        "",
        "## Interpretation",
        "",
        (
            "The observed pass rate is descriptive of this specific run. "
            "It must not be interpreted as a general reliability estimate "
            "or as evidence of improvement over a baseline. Baseline and "
            "ablation experiments are required for those comparisons."
        ),
        "",
    ])

    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


def main():
    data = load_results()
    report = build_report(data)

    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    write_markdown(report)

    print("========== EVALUATION REPORT ==========")
    print(f"Cases: {report['total_cases']}")
    print(f"Passed: {report['passed_cases']}")
    print(f"Unsupported: {report['unsupported_cases']}")
    print(f"Failed/rejected: {report['failed_or_rejected_cases']}")
    print(f"Observed pass rate: {report['observed_pass_rate_percent']}%")
    print("\nStrategy classifications:")

    for strategy, count in report["strategy_counts"].items():
        print(f"{strategy}: {count}")

    print(f"\nJSON report: {REPORT_JSON}")
    print(f"Markdown report: {REPORT_MD}")


if __name__ == "__main__":
    main()
