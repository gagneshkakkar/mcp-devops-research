
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "benchmark" / "results"

RULE_FILE = RESULTS / "baseline_rule_results.json"
SINGLE_LLM_FILE = RESULTS / "baseline_single_llm_results.json"
PROPOSED_FILE = RESULTS / "evaluation_report.json"

JSON_OUTPUT = RESULTS / "baseline_comparison.json"
MARKDOWN_OUTPUT = RESULTS / "baseline_comparison.md"


def load_json(path):
    if not path.exists():
        raise FileNotFoundError(f"Required result file not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def summarize_rule_based(data):
    summary = data.get("summary", {})
    total = data.get("total_cases", 0)
    passed = summary.get("passed", 0)
    unsupported = summary.get("unsupported_syntax_error", 0)
    errors = summary.get("error", 0)
    failed = summary.get("test_failed", 0)

    return {
        "experiment": "Rule-based baseline",
        "total_cases": total,
        "passed": passed,
        "unsupported": unsupported,
        "errors": errors,
        "test_failed": failed,
        "other_statuses": {
            key: value
            for key, value in summary.items()
            if key not in {
                "passed",
                "unsupported_syntax_error",
                "error",
                "test_failed",
            }
        },
        "pass_rate_percent": round(passed / total * 100, 2)
        if total else 0,
        "source_file": RULE_FILE.name,
    }


def summarize_single_llm(data):
    summary = data.get("summary", {})
    total = data.get("total_cases", 0)
    passed = summary.get("passed", 0)

    return {
        "experiment": "Single-LLM baseline",
        "model": data.get("model", "Not recorded"),
        "total_cases": total,
        "passed": passed,
        "unsupported": summary.get("unsupported", 0),
        "errors": summary.get("error", 0),
        "test_failed": summary.get("test_failed", 0),
        "other_statuses": {
            key: value
            for key, value in summary.items()
            if key not in {
                "passed",
                "unsupported",
                "error",
                "test_failed",
            }
        },
        "pass_rate_percent": data.get(
            "observed_pass_rate_percent",
            round(passed / total * 100, 2) if total else 0,
        ),
        "source_file": SINGLE_LLM_FILE.name,
    }


def summarize_proposed(data):
    total = data.get("total_cases", 0)
    passed = data.get("passed_cases", 0)
    unsupported = data.get("unsupported_cases", 0)
    failed = data.get("failed_or_rejected_cases", 0)

    return {
        "experiment": "Proposed multi-agent system",
        "total_cases": total,
        "passed": passed,
        "unsupported": unsupported,
        "errors": 0,
        "test_failed": failed,
        "other_statuses": {},
        "pass_rate_percent": data.get(
            "observed_pass_rate_percent",
            round(passed / total * 100, 2) if total else 0,
        ),
        "strategy_counts": data.get("strategy_counts", {}),
        "source_file": PROPOSED_FILE.name,
    }


def build_markdown(report):
    lines = [
        "# Baseline Comparison Report",
        "",
        f"Generated (UTC): {report['generated_at_utc']}",
        "",
        "## Experiment Summary",
        "",
        "| Approach | Passed | Unsupported | Errors | Test failed | Pass rate |",
        "|---|---:|---:|---:|---:|---:|",
    ]

    for item in report["experiments"]:
        lines.append(
            f"| {item['experiment']} "
            f"| {item['passed']}/{item['total_cases']} "
            f"| {item['unsupported']} "
            f"| {item['errors']} "
            f"| {item['test_failed']} "
            f"| {item['pass_rate_percent']:.1f}% |"
        )

    lines.extend([
        "",
        "## Interpretation",
        "",
        "- The rule-based baseline achieved an observed 90% pass rate.",
        "- The single-LLM baseline achieved an observed 70% pass rate.",
        "- The proposed multi-agent system achieved an observed 90% pass rate.",
        "- The rule-based baseline uses benchmark-specific deterministic rules.",
        "- The single-LLM baseline uses one direct model call per case, "
        "without multi-agent orchestration or repair retries.",
        "- The proposed-system figure comes from its saved evaluation report.",
        "",
        "## Important Limitations",
        "",
    ])

    for limitation in report["limitations"]:
        lines.append(f"- {limitation}")

    lines.extend([
        "",
        "## Source Files",
        "",
    ])

    for item in report["experiments"]:
        lines.append(f"- `{item['source_file']}`")

    lines.append("")
    return "\n".join(lines)


def main():
    rule_data = load_json(RULE_FILE)
    llm_data = load_json(SINGLE_LLM_FILE)
    proposed_data = load_json(PROPOSED_FILE)

    experiments = [
        summarize_rule_based(rule_data),
        summarize_single_llm(llm_data),
        summarize_proposed(proposed_data),
    ]

    totals = {item["total_cases"] for item in experiments}
    if len(totals) != 1:
        raise ValueError(
            "The experiments do not cover the same number of cases: "
            f"{sorted(totals)}"
        )

    report = {
        "report_type": "baseline_comparison",
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "benchmark_cases": experiments[0]["total_cases"],
        "experiments": experiments,
        "limitations": [
            "The benchmark contains only ten cases.",
            "The rule-based rules are tailored to this benchmark and "
            "should not be treated as a general-purpose repair system.",
            "The results are observed outcomes from saved runs, not "
            "averages over repeated trials.",
            "The three approaches have different repair capabilities "
            "and failure handling, so pass rate alone does not explain "
            "their behavior.",
            "The proposed-system result is taken from the saved "
            "evaluation report; no new repair experiment was run.",
            "These results do not establish statistical significance "
            "or generalization to real-world CI failures.",
        ],
    }

    JSON_OUTPUT.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    MARKDOWN_OUTPUT.write_text(
        build_markdown(report),
        encoding="utf-8",
    )

    print("========== BASELINE COMPARISON ==========")

    for item in experiments:
        print(
            f"{item['experiment']}: "
            f"{item['passed']}/{item['total_cases']} passed "
            f"({item['pass_rate_percent']:.1f}%)"
        )

    print("\nReports created:")
    print(JSON_OUTPUT)
    print(MARKDOWN_OUTPUT)


if __name__ == "__main__":
    main()
