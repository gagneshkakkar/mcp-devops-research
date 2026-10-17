
import json
import statistics
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = PROJECT_ROOT / "benchmark" / "results" / "repeated_runs"
OUTPUT_PATH = (
    PROJECT_ROOT
    / "benchmark"
    / "results"
    / "single_llm_repeated_summary.json"
)


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
    run_files = sorted(RUNS_DIR.glob("single_llm_*.json"))

    if not run_files:
        raise FileNotFoundError(
            f"No single-LLM run files found in {RUNS_DIR}"
        )

    runs = []
    for path in run_files:
        data = json.loads(path.read_text(encoding="utf-8"))

        if data.get("approach") != "single_llm":
            continue

        runs.append(data)

    if not runs:
        raise ValueError("No valid single-LLM run records found.")

    pass_rates = []
    generation_times = []
    case_elapsed_totals = []
    token_totals = []
    case_statuses = {}
    run_summaries = []

    for run in runs:
        cases = run["cases"]
        if not cases:
            continue

        passed = sum(case["status"] == "passed" for case in cases)
        pass_rate = passed / len(cases) * 100
        pass_rates.append(pass_rate)

        generations = [
            case["generation_seconds"]
            for case in cases
            if case.get("generation_seconds") is not None
        ]
        generation_times.append(sum(generations))

        case_elapsed_totals.append(
            sum(
                case["elapsed_seconds"]
                for case in cases
                if case.get("elapsed_seconds") is not None
            )
        )

        token_usage = run.get("summary", {}).get("token_usage", {})
        token_total = token_usage.get("total_tokens")
        token_totals.append(token_total)

        run_summaries.append({
            "run_id": run["run_id"],
            "pass_rate_percent": round(pass_rate, 2),
            "generation_seconds": round(sum(generations), 6),
            "total_case_elapsed_seconds": round(
                case_elapsed_totals[-1], 6
            ),
            "total_tokens": token_total,
            "status_counts": run.get("summary", {}).get(
                "status_counts", {}
            ),
        })

        for case in cases:
            case_statuses.setdefault(case["case_id"], []).append(
                case["status"]
            )

    per_case = {}
    for case_id, statuses in sorted(case_statuses.items()):
        per_case[case_id] = {
            "status_counts": {
                status: statuses.count(status)
                for status in sorted(set(statuses))
            },
            "same_outcome_in_all_runs": (
                len(statuses) == len(runs)
                and len(set(statuses)) == 1
            ),
            "passed_in_all_runs": (
                len(statuses) == len(runs)
                and all(status == "passed" for status in statuses)
            ),
        }

    report = {
        "approach": "single_llm",
        "model": runs[0].get("model_config", {}).get("model"),
        "run_count": len(runs),
        "run_ids": [run["run_id"] for run in runs],
        "pass_rate_percent": describe(pass_rates),
        "generation_seconds_per_run": describe(generation_times),
        "total_case_elapsed_seconds_per_run": describe(
            case_elapsed_totals
        ),
        "total_tokens_per_run": describe(
            [value for value in token_totals if value is not None]
        ),
        "all_runs_reported_token_usage": (
            len(token_totals) == len(runs)
            and all(value is not None for value in token_totals)
        ),
        "per_run": run_summaries,
        "per_case": per_case,
        "limitations": [
            "Results cover a custom 10-case benchmark.",
            "Only three repeated runs are included.",
            "The same local machine and model configuration were used.",
            "Generation time is the sum of per-case API-call durations, not full experiment wall-clock time.",
            "Local model warm-up, caching, and system load may affect latency.",
            "Token counts are reported by the local API and may not be comparable to other providers.",
        ],
    }

    OUTPUT_PATH.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print("========== SINGLE-LLM REPEATABILITY SUMMARY ==========")
    print(f"Runs included: {len(runs)}")

    for label, key in (
        ("Pass rate (%)", "pass_rate_percent"),
        ("Generation seconds per run", "generation_seconds_per_run"),
        ("Total case elapsed seconds per run",
         "total_case_elapsed_seconds_per_run"),
        ("Total tokens per run", "total_tokens_per_run"),
    ):
        stats = report[key]
        print(f"\n{label}:")
        print(f"  Mean: {stats['mean']}")
        print(f"  Median: {stats['median']}")
        print(
            "  Sample standard deviation: "
            f"{stats['sample_standard_deviation']}"
        )

    print("\nPer-run results:")
    for item in run_summaries:
        print(
            f"  {item['run_id'][:8]}: "
            f"pass={item['pass_rate_percent']}%, "
            f"generation={item['generation_seconds']}s, "
            f"tokens={item['total_tokens']}"
        )

    print(f"\nSummary saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
