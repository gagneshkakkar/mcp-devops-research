
import json
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = PROJECT_ROOT / "benchmark" / "results" / "repeated_runs"
OUTPUT_PATH = (
    PROJECT_ROOT
    / "benchmark"
    / "results"
    / "proposed_repeated_summary.json"
)


def mean_or_none(values):
    return statistics.mean(values) if values else None


def median_or_none(values):
    return statistics.median(values) if values else None


def sample_sd_or_none(values):
    if len(values) < 2:
        return None
    return statistics.stdev(values)


def summarize_metric(values):
    return {
        "mean": mean_or_none(values),
        "median": median_or_none(values),
        "sample_standard_deviation": sample_sd_or_none(values),
        "observations": len(values),
    }


def load_runs():
    paths = sorted(RUNS_DIR.glob("proposed_*.json"))

    if len(paths) != 3:
        raise SystemExit(
            f"Expected exactly 3 proposed-system run files, "
            f"but found {len(paths)} in {RUNS_DIR}"
        )

    runs = []

    for path in paths:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data.get("cases"), list):
            raise SystemExit(f"Missing cases list in {path.name}")

        if len(data["cases"]) != 10:
            raise SystemExit(
                f"Expected 10 cases in {path.name}; "
                f"found {len(data['cases'])}"
            )

        runs.append({
            "filename": path.name,
            "data": data,
        })

    return runs


def case_outcome(case):
    # Preserve unsupported syntax as its own outcome.
    return case.get("status", "unknown")


def main():
    runs = load_runs()

    run_summaries = []
    pass_rates = []
    elapsed_totals = []
    llm_call_totals = []

    all_case_ids = set()

    for run in runs:
        data = run["data"]
        cases = data["cases"]

        case_ids = [case.get("case_id") for case in cases]

        if len(set(case_ids)) != len(case_ids):
            raise SystemExit(
                f"Duplicate case IDs found in {run['filename']}"
            )

        all_case_ids.update(case_ids)

        passed = sum(
            1 for case in cases
            if case_outcome(case) == "passed"
        )
        pass_rate = passed / len(cases) * 100
        pass_rates.append(pass_rate)

        elapsed_values = [
            case["elapsed_seconds"]
            for case in cases
            if isinstance(case.get("elapsed_seconds"), (int, float))
            and not isinstance(case.get("elapsed_seconds"), bool)
        ]

        total_elapsed = sum(elapsed_values) if elapsed_values else None

        if total_elapsed is not None:
            elapsed_totals.append(total_elapsed)

        llm_call_total = sum(
            case.get("llm_calls", 0)
            for case in cases
            if isinstance(case.get("llm_calls", 0), int)
            and not isinstance(case.get("llm_calls", 0), bool)
        )
        llm_call_totals.append(llm_call_total)

        status_counts = dict(Counter(
            case_outcome(case) for case in cases
        ))

        run_summaries.append({
            "filename": run["filename"],
            "run_id": data.get("run_id"),
            "started_at_utc": data.get("started_at_utc"),
            "completed_at_utc": data.get("completed_at_utc"),
            "total_cases": len(cases),
            "passed_cases": passed,
            "pass_rate_percent": pass_rate,
            "total_case_elapsed_seconds": total_elapsed,
            "llm_calls_recorded": llm_call_total,
            "outcome_counts": status_counts,
        })

    # Compare outcomes by case ID across all three runs.
    per_case = []

    for case_id in sorted(all_case_ids):
        outcomes = []

        for run in runs:
            matching = [
                case for case in run["data"]["cases"]
                if case.get("case_id") == case_id
            ]

            if not matching:
                outcomes.append({
                    "run_file": run["filename"],
                    "outcome": "missing_case",
                })
            else:
                outcomes.append({
                    "run_file": run["filename"],
                    "outcome": case_outcome(matching[0]),
                })

        outcome_values = [item["outcome"] for item in outcomes]

        per_case.append({
            "case_id": case_id,
            "outcomes": outcomes,
            "consistent_across_runs": (
                len(set(outcome_values)) == 1
            ),
        })

    consistency_count = sum(
        1 for item in per_case
        if item["consistent_across_runs"]
    )

    report = {
        "report_type": "proposed_system_repeatability",
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "approach": "Proposed multi-agent repair pipeline",
        "number_of_runs": len(runs),
        "dataset_case_count": 10,
        "run_results": run_summaries,
        "statistics": {
            "pass_rate_percent": summarize_metric(pass_rates),
            "total_case_elapsed_seconds": summarize_metric(
                elapsed_totals
            ),
            "llm_calls_recorded": summarize_metric(
                llm_call_totals
            ),
        },
        "case_consistency": {
            "cases_with_consistent_outcomes": consistency_count,
            "total_cases_compared": len(per_case),
            "all_cases_consistent": (
                consistency_count == len(per_case)
            ),
            "per_case": per_case,
        },
        "measurement_notes": [
            (
                "Elapsed time is the sum of recorded per-case "
                "elapsed times; it may exclude process startup."
            ),
            (
                "Token counts are unavailable from the current "
                "proposed pipeline and must not be interpreted as zero."
            ),
            (
                "The recorded LLM call count reflects instrumented "
                "repair-generation function invocations, not necessarily "
                "every underlying model request."
            ),
            (
                "Three repeated runs on a 10-case custom benchmark "
                "provide preliminary repeatability evidence, not "
                "proof of generalization to unseen repositories."
            ),
        ],
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_PATH.open("w", encoding="utf-8") as file:
        json.dump(report, file, indent=2, ensure_ascii=False)
        file.write("\n")

    print("========== PROPOSED SYSTEM REPEATABILITY SUMMARY ==========")
    print(f"Runs analyzed: {len(runs)}")

    for run in run_summaries:
        print(
            f"{run['filename']}: "
            f"{run['passed_cases']}/{run['total_cases']} passed "
            f"({run['pass_rate_percent']:.1f}%), "
            f"elapsed={run['total_case_elapsed_seconds']}"
        )

    print("\nPass-rate statistics:")
    print(json.dumps(
        report["statistics"]["pass_rate_percent"],
        indent=2,
    ))

    print("\nElapsed-time statistics:")
    print(json.dumps(
        report["statistics"]["total_case_elapsed_seconds"],
        indent=2,
    ))

    print(
        "\nConsistent case outcomes: "
        f"{consistency_count}/{len(per_case)}"
    )

    print(f"\nSummary saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
