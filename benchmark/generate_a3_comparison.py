
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"


def load_json(filename):
    path = RESULTS / filename

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def get_case_records(data):
    records = data.get("results")

    if isinstance(records, list):
        return records

    records = data.get("cases")

    if isinstance(records, list):
        return records

    return []


def get_passed_count(data):
    if isinstance(data.get("passed"), int):
        return data["passed"]

    if isinstance(data.get("passed_cases"), int):
        return data["passed_cases"]

    summary = data.get("summary", {})

    if isinstance(summary, dict) and isinstance(
        summary.get("passed"), int
    ):
        return summary["passed"]

    records = get_case_records(data)

    if records:
        return sum(
            record.get("status") == "passed"
            or record.get("result") == "passed"
            for record in records
        )

    return None


def summarize(name, filename, limitation):
    data = load_json(filename)

    total = data.get(
        "total_cases",
        data.get("cases_recorded"),
    )
    passed = get_passed_count(data)

    if not isinstance(total, int):
        total = len(get_case_records(data))

    if passed is None:
        raise ValueError(
            f"Could not determine passed count in {filename}"
        )

    return {
        "approach": name,
        "source_file": filename,
        "cases": total,
        "passed": passed,
        "pass_rate_percent": (
            round(100 * passed / total, 2) if total else 0
        ),
        "limitation": limitation,
    }


def summarize_proposed_system():
    data = load_json("evaluation_report.json")

    total = data["total_cases"]
    passed = data["passed_cases"]

    return {
        "approach": "Proposed multi-agent repair pipeline",
        "source_file": "evaluation_report.json",
        "cases": total,
        "passed": passed,
        "pass_rate_percent": data["observed_pass_rate_percent"],
        "limitation": (
            "Uses the saved proposed-system evaluation snapshot; "
            "no experiment was rerun to generate this comparison."
        ),
    }


def summarize_instrumented_rag():
    data = load_json("rag_instrumented_results.json")

    records = get_case_records(data)
    total = data.get("total_cases", len(records))
    passed = get_passed_count(data)

    if passed is None:
        raise ValueError(
            "Could not determine passed count in "
            "rag_instrumented_results.json"
        )

    return {
        "experiment": data.get("experiment"),
        "run_id": data.get("run_id"),
        "source_file": "rag_instrumented_results.json",
        "started_at_utc": data.get("started_at_utc"),
        "completed_at_utc": data.get("completed_at_utc"),
        "model": data.get("model"),
        "embedding_model": data.get("embedding_model"),
        "retrieval_method": data.get("retrieval_method"),
        "top_k": data.get("top_k"),
        "cases": total,
        "passed": passed,
        "pass_rate_percent": (
            round(100 * passed / total, 2) if total else 0
        ),
        "elapsed_seconds": data.get("elapsed_seconds"),
        "aggregate_token_usage": data.get(
            "aggregate_token_usage"
        ),
        "summary": data.get("summary", {}),
        "per_case_metrics": [
            {
                "case_id": record.get("id"),
                "status": record.get("status"),
                "elapsed_seconds": record.get("elapsed_seconds"),
                "retrieval_seconds": record.get("retrieval_seconds"),
                "generation_seconds": record.get("generation_seconds"),
                "evaluation_seconds": record.get("evaluation_seconds"),
                "token_usage": record.get("token_usage"),
            }
            for record in records
        ],
        "interpretation": (
            "A separate instrumented repeat of the semantic RAG "
            "approach. It is reported as a repeat run, not as a new "
            "approach or an independent baseline."
        ),
        "limitations": [
            "The result is from one run on the custom 10-case dataset.",
            "The original RAG retrieval corpus allows target-case "
            "self-retrieval.",
            "Token usage depends on what the local model endpoint reports.",
            "Elapsed time depends on local hardware and system load.",
            "The observed pass rate does not establish statistical "
            "significance or generalization to unseen projects.",
        ],
    }


def summarize_f10_follow_up():
    data = load_json("f10_prompt_test.json")

    return {
        "experiment": data["experiment"],
        "source_file": "f10_prompt_test.json",
        "case_id": data["case_id"],
        "status": data["status"],
        "expected_when_unset": data["expected_when_unset"],
        "actual_when_unset": data["actual_when_unset"],
        "expected_when_set": data["expected_when_set"],
        "actual_when_set": data["actual_when_set"],
        "interpretation": (
            "A targeted single-case follow-up, not a 10-case "
            "benchmark result. Its status must not be compared "
            "directly with the overall pass rates."
        ),
    }


def main():
    comparisons = [
        summarize(
            "Rule-based baseline",
            "baseline_rule_results.json",
            "Uses benchmark-specific hand-coded rules, not a general repair system.",
        ),
        summarize(
            "Single LLM",
            "baseline_single_llm_results.json",
            "One local Qwen call per case; no retries or fallbacks.",
        ),
        summarize(
            "LLM + semantic RAG",
            "rag_results.json",
            "Historical run. The retrieval corpus includes target-case "
            "broken metadata/source, allowing self-retrieval.",
        ),
        summarize(
            "LLM + semantic RAG + MCP",
            "mcp_rag_results.json",
            "Single pilot run; two cases failed behavioral evaluation.",
        ),
        summarize(
            "LLM + leave-one-case-out semantic RAG",
            "rag_loco_results.json",
            "Excludes each target case from retrieval. The observed result "
            "comes from one 10-case run and does not establish statistical "
            "significance or generalization to unseen projects.",
        ),
        summarize_proposed_system(),
    ]

    instrumented_rag = summarize_instrumented_rag()
    f10_follow_up = summarize_f10_follow_up()

    payload = {
        "title": (
            "Benchmark Comparison: Rule-Based, LLM, RAG, MCP, "
            "LOCO RAG, and Proposed System"
        ),
        "dataset_size": 10,
        "interpretation": (
            "Descriptive comparison of saved pilot runs on a small custom "
            "benchmark. These results do not establish statistical significance "
            "or prove that MCP or LOCO retrieval alone caused any observed "
            "difference."
        ),
        "approaches": comparisons,
        "instrumented_repeat_run": instrumented_rag,
        "targeted_follow_up": f10_follow_up,
    }

    json_path = RESULTS / "a3_comparison.json"
    markdown_path = RESULTS / "a3_comparison.md"

    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    lines = [
        "# Benchmark Comparison",
        "",
        "Descriptive comparison of saved pilot runs on a custom 10-case dataset.",
        "",
        "| Approach | Passed | Cases | Pass rate |",
        "|---|---:|---:|---:|",
    ]

    for item in comparisons:
        lines.append(
            f"| {item['approach']} | {item['passed']} | "
            f"{item['cases']} | {item['pass_rate_percent']:.1f}% |"
        )

    lines.extend([
        "",
        "## Instrumented Repeat Run: LLM + Semantic RAG",
        "",
        f"- Run ID: `{instrumented_rag['run_id']}`",
        f"- Source: `{instrumented_rag['source_file']}`",
        f"- Started (UTC): `{instrumented_rag['started_at_utc']}`",
        f"- Completed (UTC): `{instrumented_rag['completed_at_utc']}`",
        f"- Model: `{instrumented_rag['model']}`",
        f"- Embedding model: `{instrumented_rag['embedding_model']}`",
        f"- Top K: {instrumented_rag['top_k']}",
        f"- Passed: {instrumented_rag['passed']}/{instrumented_rag['cases']}",
        f"- Pass rate: {instrumented_rag['pass_rate_percent']:.1f}%",
        f"- Total elapsed time: {instrumented_rag['elapsed_seconds']} seconds",
        "",
        "### Aggregate token usage",
        "",
    ])

    for field, value in instrumented_rag[
        "aggregate_token_usage"
    ].items():
        lines.append(f"- {field}: {value}")

    lines.extend([
        "",
        "### Per-case timing and token usage",
        "",
        "| Case | Status | Total (s) | Retrieval (s) | Generation (s) | Evaluation (s) | Total tokens |",
        "|---|---|---:|---:|---:|---:|---:|",
    ])

    for record in instrumented_rag["per_case_metrics"]:
        usage = record.get("token_usage") or {}
        total_tokens = usage.get("total_tokens")

        lines.append(
            f"| {record['case_id']} "
            f"| {record['status']} "
            f"| {record['elapsed_seconds']} "
            f"| {record['retrieval_seconds']} "
            f"| {record['generation_seconds']} "
            f"| {record['evaluation_seconds']} "
            f"| {total_tokens} |"
        )

    lines.extend([
        "",
        instrumented_rag["interpretation"],
        "",
        "Limitations of the instrumented run:",
        "",
    ])

    for limitation in instrumented_rag["limitations"]:
        lines.append(f"- {limitation}")

    lines.extend([
        "",
        "## Overall Comparison Limitations",
        "",
        "- Each overall result is from a saved pilot run on a small custom dataset.",
        "- The rule-based baseline uses benchmark-specific rules.",
        "- The original RAG corpus contains target-case broken evidence, allowing self-retrieval.",
        "- LOCO excludes the target case, but the remaining corpus is still drawn from the same 10-case benchmark.",
        "- The MCP experiment measures the combined LLM + RAG + MCP setup; it does not isolate the causal contribution of MCP.",
        "- The proposed-system figure comes from the saved evaluation snapshot.",
        "- These single pilot runs do not establish statistical significance.",
        "- The instrumented RAG run is a repeat measurement, not an additional independent approach.",
        "",
        "## Targeted Follow-up: F10 Prompt Experiment",
        "",
        f"- Status: **{f10_follow_up['status']}**",
        f"- Case: {f10_follow_up['case_id']}",
        f"- When the variable is unset: `{f10_follow_up['actual_when_unset']}`",
        f"- When the variable is set: `{f10_follow_up['actual_when_set']}`",
        "",
        f10_follow_up["interpretation"],
        "",
        "This targeted test is reported separately and is not included as an overall benchmark row.",
        "",
    ])

    for item in comparisons:
        lines.extend([
            f"### {item['approach']}",
            "",
            item["limitation"],
            "",
        ])

    markdown_path.write_text(
        "\n".join(lines).rstrip() + "\n",
        encoding="utf-8",
    )

    print("Comparison report generated from saved results.")
    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")

    print("\nOverall benchmark pass rates:")
    for item in comparisons:
        print(
            f"- {item['approach']}: "
            f"{item['passed']}/{item['cases']} "
            f"({item['pass_rate_percent']:.1f}%)"
        )

    print("\nInstrumented RAG repeat run:")
    print(
        f"- Pass rate: {instrumented_rag['passed']}/"
        f"{instrumented_rag['cases']} "
        f"({instrumented_rag['pass_rate_percent']:.1f}%)"
    )
    print(
        "- Elapsed seconds:",
        instrumented_rag["elapsed_seconds"],
    )
    print(
        "- Aggregate token usage:",
        instrumented_rag["aggregate_token_usage"],
    )
    print("- Reported separately from the historical RAG run.")

    print("\nTargeted F10 follow-up:")
    print(f"- Status: {f10_follow_up['status']}")
    print("- Reported separately; not counted as a 10-case pass rate.")


if __name__ == "__main__":
    main()
