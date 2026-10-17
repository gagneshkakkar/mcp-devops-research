
import json
import statistics
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = PROJECT_ROOT / "benchmark" / "results" / "repeated_runs"
OUTPUT_PATH = (
    PROJECT_ROOT
    / "benchmark"
    / "results"
    / "rule_based_repeated_summary.json"
)


def load_runs():
    files = sorted(RUNS_DIR.glob("rule_based_*.json"))

    if not files:
        raise FileNotFoundError(
            f"No rule-based repeated-run files found in {RUNS_DIR}"
        )

    runs = []

    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))

        if data.get("approach") != "rule_based":
            continue

        runs.append(data)

    if not runs:
        raise ValueError("No valid rule-based runs were found.")

    return runs


def describe(values):
    if not values:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "sample_standard_deviation": None,
        }

    return {
        "count": len(values),
        "mean": round(statistics.mean(values), 6),
        "median": round(statistics.median(values), 6),
        "sample_standard_deviation": (
            round(statistics.stdev(values), 6)
            if len(values) > 1
            else None
        ),
    }


def main():
    runs = load_runs()

    pass_rates = []
    total_elapsed = []
    case_times = {}
    case_statuses = {}

    for run in runs:
        cases = run["cases"]

        if not cases:
            continue

        passed = sum(
            case["status"] == "passed"
            for case in cases
        )
        pass_rates.append(round(passed / len(cases) * 100, 2))

        elapsed = [
            case["elapsed_seconds"]
            for case in cases
            if case["elapsed_seconds"] is not None
        ]
        total_elapsed.append(sum(elapsed))

        for case in cases:
            case_id = case["case_id"]
            case_times.setdefault(case_id, []).append(
                case["elapsed_seconds"]
            )
            case_statuses.setdefault(case_id, []).append(
                case["status"]
            )

    per_case = {}

    for case_id in sorted(case_statuses):
        statuses = case_statuses[case_id]
        times = [
            value
            for value in case_times[case_id]
            if value is not None
        ]

        per_case[case_id] = {
            "status_counts": {
                status: statuses.count(status)
                for status in sorted(set(statuses))
            },
            "passed_in_all_runs": (
                len(statuses) == len(runs)
                and all(status == "passed" for status in statuses)
            ),
            "elapsed_seconds": describe(times),
        }

    report = {
        "approach": "rule_based",
        "run_count": len(runs),
        "run_ids": [run["run_id"] for run in runs],
        "pass_rate_percent": describe(pass_rates),
        "total_case_elapsed_seconds_per_run": describe(total_elapsed),
        "per_case": per_case,
        "limitations": [
            "Only repeated rule-based runs are summarized.",
            "The benchmark contains 10 custom cases.",
            "Repeated runs on the same machine are not independent hardware trials.",
            "Timing can vary with operating-system scheduling and filesystem caching.",
            "The reported elapsed time sums per-case measurements and excludes process startup.",
        ],
    }

    OUTPUT_PATH.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print("========== RULE-BASED REPEATABILITY SUMMARY ==========")
    print(f"Runs included: {len(runs)}")

    for label, key in (
        ("Pass rate (%)", "pass_rate_percent"),
        ("Total case time (seconds)", "total_case_elapsed_seconds_per_run"),
    ):
        stats = report[key]
        print(f"\n{label}:")
        print(f"  Mean: {stats['mean']}")
        print(f"  Median: {stats['median']}")
        print(
            "  Sample standard deviation: "
            f"{stats['sample_standard_deviation']}"
        )

    print("\nPer-case status consistency:")
    for case_id, values in per_case.items():
        print(
            f"  {case_id}: {values['status_counts']} | "
            f"Passed in all runs: {values['passed_in_all_runs']}"
        )

    print(f"\nSummary saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
