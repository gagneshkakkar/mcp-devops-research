
import json
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from benchmark.run_rule_baseline import (
    BENCHMARK_ROOT,
    apply_rule,
    evaluate,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNS_ROOT = PROJECT_ROOT / "benchmark" / "results" / "repeated_runs"
WORKSPACES_ROOT = (
    PROJECT_ROOT / "benchmark" / "baseline_workspaces" / "rule_repeated"
)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def run_case(case_dir):
    case_id = case_dir.name
    metadata = read_json(case_dir / "metadata.json")
    source_path = case_dir / "broken" / "calculator.py"
    workspace_path = WORKSPACES_ROOT / case_id / "calculator.py"

    started = time.perf_counter()
    record = {
        "case_id": case_id,
        "status": "not_started",
        "elapsed_seconds": None,
        "llm_calls": 0,
        "token_usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
        "retrieval_seconds": None,
        "generation_seconds": None,
        "mcp_seconds": None,
        "evaluation_seconds": None,
        "repair_strategy": "predefined_rule",
        "repair_applied": False,
        "error": None,
    }

    try:
        workspace_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, workspace_path)

        source = workspace_path.read_text(encoding="utf-8")

        try:
            compile(source, str(workspace_path), "exec")
        except SyntaxError as error:
            record["status"] = "unsupported_syntax_error"
            record["error"] = str(error)
            return record

        repaired_source, message = apply_rule(case_id, source, metadata)
        record["rule_message"] = message

        if repaired_source is None:
            record["status"] = (
                "unsupported" if case_id == "F06" else "error"
            )
            record["error"] = message
            return record

        compile(repaired_source, str(workspace_path), "exec")
        workspace_path.write_text(repaired_source, encoding="utf-8")
        record["repair_applied"] = True

        evaluation_started = time.perf_counter()
        behavior = evaluate(workspace_path, metadata)
        record["evaluation_seconds"] = (
            time.perf_counter() - evaluation_started
        )

        record["behavior"] = behavior
        record["status"] = (
            "passed" if behavior["passed"] else "test_failed"
        )

    except Exception as error:
        record["status"] = "error"
        record["error"] = f"{type(error).__name__}: {error}"

    finally:
        record["elapsed_seconds"] = time.perf_counter() - started

    return record


def main():
    RUNS_ROOT.mkdir(parents=True, exist_ok=True)

    case_directories = sorted(
        path
        for path in BENCHMARK_ROOT.iterdir()
        if path.is_dir() and path.name.startswith("F")
    )

    run_id = str(uuid.uuid4())
    started_at = utc_now()

    results = []
    for case_dir in case_directories:
        print(f"Running {case_dir.name}...")
        record = run_case(case_dir)
        results.append(record)
        print(
            f"  Status: {record['status']} | "
            f"Elapsed: {record['elapsed_seconds']:.6f}s"
        )

    completed_at = utc_now()
    passed = sum(item["status"] == "passed" for item in results)

    output = {
        "run_id": run_id,
        "approach": "rule_based",
        "started_at_utc": started_at,
        "completed_at_utc": completed_at,
        "model_config": {
            "provider": None,
            "model": None,
            "temperature": None,
            "llm_calls": 0,
            "notes": "Deterministic benchmark-specific rules; no LLM.",
        },
        "dataset": {
            "name": "custom_10_case_ci_failure_benchmark",
            "case_count": len(results),
            "case_ids": [item["case_id"] for item in results],
        },
        "cases": results,
        "summary": {
            "passed": passed,
            "total_cases": len(results),
            "pass_rate_percent": (
                round(passed / len(results) * 100, 2)
                if results
                else 0.0
            ),
            "status_counts": {
                status: sum(
                    item["status"] == status for item in results
                )
                for status in sorted(
                    {item["status"] for item in results}
                )
            },
            "total_elapsed_seconds": sum(
                item["elapsed_seconds"] or 0 for item in results
            ),
        },
        "limitations": [
            "Rules are specifically written for this custom benchmark.",
            "This is not a general-purpose repair baseline.",
            "F06 syntax-error repair is intentionally unsupported.",
            "No LLM calls or token usage occur in this approach.",
        ],
    }

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = RUNS_ROOT / f"rule_based_{timestamp}_{run_id[:8]}.json"

    if output_path.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing run: {output_path}"
        )

    output_path.write_text(
        json.dumps(output, indent=2),
        encoding="utf-8",
    )

    print("\n========== REPEATED RULE BASELINE ==========")
    print(f"Run ID: {run_id}")
    print(f"Cases: {len(results)}")
    print(f"Passed: {passed}")
    print(f"Pass rate: {output['summary']['pass_rate_percent']}%")
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()
