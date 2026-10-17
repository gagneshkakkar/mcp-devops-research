
import json
import statistics
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

RUNS_DIR = (
    PROJECT_ROOT
    / "benchmark"
    / "results"
    / "repeated_runs"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "benchmark"
    / "results"
    / "rag_repeated_summary.json"
)


def mean_or_none(values):
    return statistics.mean(values) if values else None


def median_or_none(values):
    return statistics.median(values) if values else None


def sample_sd_or_none(values):
    if len(values) < 2:
        return None
    return statistics.stdev(values)


def rounded(value):
    if value is None:
        return None
    return round(value, 6)


def summarize_metric(values):
    return {
        "mean": rounded(mean_or_none(values)),
        "median": rounded(median_or_none(values)),
        "sample_standard_deviation": rounded(
            sample_sd_or_none(values)
        ),
        "minimum": rounded(min(values)) if values else None,
        "maximum": rounded(max(values)) if values else None,
        "observations": len(values),
    }


def get_token_total(run, token_name):
    usage = run.get("summary", {}).get("token_usage", {})
    value = usage.get(token_name)

    if isinstance(value, (int, float)):
        return value

    case_values = [
        case.get("token_usage", {}).get(token_name)
        for case in run.get("cases", [])
    ]

    if (
        case_values
        and all(isinstance(v, (int, float)) for v in case_values)
    ):
        return sum(case_values)

    return None


def main():
    files = sorted(RUNS_DIR.glob("llm_rag_*.json"))

    if not files:
        raise FileNotFoundError(
            f"No RAG repeated-run files found in {RUNS_DIR}"
        )

    runs = []

    for path in files:
        with path.open("r", encoding="utf-8") as file:
            run = json.load(file)

        if run.get("approach") != "llm_rag":
            continue

        runs.append({
            "file": path.name,
            "data": run,
        })

    if not runs:
        raise ValueError("No valid llm_rag runs were found.")

    pass_rates = []
    elapsed_times = []
    retrieval_times = []
    generation_times = []
    corpus_load_times = []
    prompt_tokens = []
    completion_tokens = []
    total_tokens = []
    case_outcomes = {}

    for entry in runs:
        run = entry["data"]
        cases = run.get("cases", [])
        summary = run.get("summary", {})

        total_cases = len(cases)
        passed = sum(
            case.get("status") == "passed"
            for case in cases
        )

        pass_rate = (
            passed / total_cases * 100
            if total_cases else 0.0
        )
        pass_rates.append(pass_rate)

        # Sum per-case elapsed times. This is not process wall time.
        elapsed_values = [
            case["elapsed_seconds"]
            for case in cases
            if isinstance(case.get("elapsed_seconds"), (int, float))
        ]
        if len(elapsed_values) == total_cases:
            elapsed_times.append(sum(elapsed_values))

        retrieval_values = [
            case["retrieval_seconds"]
            for case in cases
            if isinstance(case.get("retrieval_seconds"), (int, float))
        ]
        if len(retrieval_values) == total_cases:
            retrieval_times.append(sum(retrieval_values))

        generation_values = [
            case["generation_seconds"]
            for case in cases
            if isinstance(case.get("generation_seconds"), (int, float))
        ]
        if len(generation_values) == total_cases:
            generation_times.append(sum(generation_values))

        corpus_time = summary.get("corpus_load_seconds")
        if isinstance(corpus_time, (int, float)):
            corpus_load_times.append(corpus_time)

        for token_name, destination in [
            ("prompt_tokens", prompt_tokens),
            ("completion_tokens", completion_tokens),
            ("total_tokens", total_tokens),
        ]:
            value = get_token_total(run, token_name)
            if value is not None:
                destination.append(value)

        for case in cases:
            case_id = case.get("case_id", "UNKNOWN")
            case_outcomes.setdefault(case_id, []).append(
                case.get("status", "missing")
            )

    per_case = {}

    for case_id in sorted(case_outcomes):
        outcomes = case_outcomes[case_id]
        counts = dict(Counter(outcomes))

        per_case[case_id] = {
            "status_counts": counts,
            "consistent_across_runs": len(counts) == 1,
            "runs_observed": len(outcomes),
        }

    output = {
        "experiment": "Repeated LLM + Semantic RAG Evaluation",
        "approach": "llm_rag",
        "number_of_runs": len(runs),
        "run_files": [entry["file"] for entry in runs],
        "configuration": {
            "model": runs[0]["data"].get(
                "model_config", {}
            ).get("model"),
            "embedding_model": runs[0]["data"].get(
                "model_config", {}
            ).get("embedding_model"),
            "top_k": runs[0]["data"].get(
                "model_config", {}
            ).get("top_k"),
            "dataset": runs[0]["data"].get(
                "dataset", {}
            ).get("name"),
        },
        "metrics": {
            "pass_rate_percent": summarize_metric(pass_rates),
            "total_per_case_elapsed_seconds": summarize_metric(
                elapsed_times
            ),
            "total_retrieval_seconds": summarize_metric(
                retrieval_times
            ),
            "total_generation_seconds": summarize_metric(
                generation_times
            ),
            "corpus_load_seconds": summarize_metric(
                corpus_load_times
            ),
            "prompt_tokens": summarize_metric(prompt_tokens),
            "completion_tokens": summarize_metric(
                completion_tokens
            ),
            "total_tokens": summarize_metric(total_tokens),
        },
        "per_case_outcomes": per_case,
        "limitations": [
            "The benchmark contains ten custom cases.",
            "Three repetitions do not establish broad generalizability.",
            "Latency may vary with model warm-up, caching, and system load.",
            "Elapsed time is the sum of per-case elapsed times, not full process wall-clock time.",
            "Corpus loading is measured separately from per-case retrieval.",
            "Token counts are included only when reported by the API.",
            "Pass rate measures the benchmark's behavioral check, not production readiness.",
        ],
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(output, indent=2),
        encoding="utf-8",
    )

    print("========== RAG REPEATABILITY SUMMARY ==========")
    print(f"Runs included: {len(runs)}")

    for metric_name in [
        "pass_rate_percent",
        "total_per_case_elapsed_seconds",
        "total_retrieval_seconds",
        "total_generation_seconds",
        "total_tokens",
    ]:
        print(f"\n{metric_name}:")
        print(json.dumps(
            output["metrics"][metric_name],
            indent=2,
        ))

    print("\nPer-case consistency:")
    for case_id, result in per_case.items():
        print(
            f"  {case_id}: {result['status_counts']} "
            f"| consistent={result['consistent_across_runs']}"
        )

    print(f"\nSaved: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
