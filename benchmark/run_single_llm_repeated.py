
import json
import re
import shutil
import statistics
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_ROOT = PROJECT_ROOT / "benchmark" / "failures"

WORKSPACES_ROOT = (
    PROJECT_ROOT
    / "benchmark"
    / "baseline_workspaces"
    / "single_llm_repeated"
)

RUNS_ROOT = (
    PROJECT_ROOT
    / "benchmark"
    / "results"
    / "repeated_runs"
)

MODEL_NAME = "qwen2.5-coder:7b"
OLLAMA_BASE_URL = "http://localhost:11434/v1"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def clean_model_response(content):
    if not content:
        raise ValueError("The model returned an empty response.")

    content = content.strip()
    content = re.sub(
        r"\A```(?:python)?[ \t]*\r?\n",
        "",
        content,
        count=1,
        flags=re.IGNORECASE,
    )
    content = re.sub(
        r"\r?\n```[ \t]*\Z",
        "",
        content,
        count=1,
    )
    content = content.strip()

    if not content:
        raise ValueError("No Python source remained after cleaning.")

    return content + "\n"


def prepare_workspace(case_id):
    source_path = (
        BENCHMARK_ROOT / case_id / "broken" / "calculator.py"
    )
    workspace_path = (
        WORKSPACES_ROOT / case_id / "calculator.py"
    )

    if not source_path.is_file():
        raise FileNotFoundError(
            f"Broken source missing: {source_path}"
        )

    workspace_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, workspace_path)
    return workspace_path


def generate_repair(client, case_id, title, function_name, source):
    prompt = f"""
You are a Python code repair model.

Repair the supplied broken Python file.

Benchmark case: {case_id}
Failure description: {title}
Target function: {function_name}

Rules:
1. Return the COMPLETE corrected Python file.
2. Return Python source code only, without Markdown fences.
3. Preserve unrelated functions and behavior.
4. Do not modify tests or benchmark metadata.
5. Do not hardcode the expected test output.
6. Do not install packages or access the network.
7. Fix the underlying defect.
8. You may fix syntax, imports, logic, dependencies,
   runtime errors, and configuration handling.
9. Do not assume the expected test output.

Broken Python file:
--------------------
{source}
--------------------

Return the complete corrected Python file now.
"""

    started = time.perf_counter()
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    generation_seconds = time.perf_counter() - started

    content = clean_model_response(
        response.choices[0].message.content
    )

    usage = getattr(response, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", None)
    completion_tokens = getattr(usage, "completion_tokens", None)
    total_tokens = getattr(usage, "total_tokens", None)

    return {
        "source": content,
        "generation_seconds": generation_seconds,
        "token_usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        },
    }


def evaluate_behavior(source_path, metadata):
    source = source_path.read_text(encoding="utf-8")
    compiled = compile(source, str(source_path), "exec")
    namespace = {"__name__": "single_llm_repeated_benchmark"}
    exec(compiled, namespace)

    function_name = metadata["function"]
    if function_name not in namespace:
        raise ValueError(
            f"Function {function_name!r} was not found "
            "in the repaired file."
        )

    actual = namespace[function_name](**metadata["input"])
    expected = metadata["expected_output"]

    return {
        "passed": actual == expected,
        "actual_output": actual,
        "expected_output": expected,
        "actual_exception": None,
    }


def run_case(client, case_dir):
    case_id = case_dir.name
    metadata = read_json(case_dir / "metadata.json")
    started = time.perf_counter()

    record = {
        "case_id": case_id,
        "title": metadata["title"],
        "status": "not_started",
        "elapsed_seconds": None,
        "llm_calls": 0,
        "token_usage": {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
        },
        "retrieval_seconds": None,
        "generation_seconds": None,
        "mcp_seconds": None,
        "evaluation_seconds": None,
        "repair_strategy": "single_llm_full_file",
        "repair_attempted": False,
        "repair_generated": False,
        "repair_applied": False,
        "tests_passed": False,
        "error": None,
    }

    try:
        workspace_path = prepare_workspace(case_id)
        original_source = workspace_path.read_text(encoding="utf-8")

        record["repair_attempted"] = True
        record["llm_calls"] = 1

        generation = generate_repair(
            client=client,
            case_id=case_id,
            title=metadata["title"],
            function_name=metadata["function"],
            source=original_source,
        )

        record["repair_generated"] = True
        record["generation_seconds"] = generation["generation_seconds"]
        record["token_usage"] = generation["token_usage"]

        repaired_source = generation["source"]
        compile(repaired_source, str(workspace_path), "exec")
        workspace_path.write_text(repaired_source, encoding="utf-8")
        record["repair_applied"] = True

        evaluation_started = time.perf_counter()
        behavior = evaluate_behavior(workspace_path, metadata)
        record["evaluation_seconds"] = (
            time.perf_counter() - evaluation_started
        )

        record["behavior"] = behavior
        record["tests_passed"] = behavior["passed"]
        record["status"] = (
            "passed" if behavior["passed"] else "test_failed"
        )

    except Exception as error:
        record["status"] = "error"
        record["error"] = f"{type(error).__name__}: {error}"
        print(f"  Error: {record['error']}")
        traceback.print_exc()

    finally:
        record["elapsed_seconds"] = time.perf_counter() - started

    return record


def main():
    RUNS_ROOT.mkdir(parents=True, exist_ok=True)

    client = OpenAI(
        base_url=OLLAMA_BASE_URL,
        api_key="ollama",
        timeout=180.0,
        max_retries=0,
    )

    case_directories = sorted(
        path
        for path in BENCHMARK_ROOT.iterdir()
        if path.is_dir() and path.name.startswith("F")
    )

    run_id = str(uuid.uuid4())
    started_at = utc_now()
    results = []

    print("========== SINGLE-LLM REPEATED RUN ==========")
    print(f"Run ID: {run_id}")
    print(f"Model: {MODEL_NAME}")
    print("One model call per case; no retries or fallbacks.")

    for case_dir in case_directories:
        print(f"\nRunning {case_dir.name}...")
        record = run_case(client, case_dir)
        results.append(record)

        print(
            f"  Status: {record['status']} | "
            f"Elapsed: {record['elapsed_seconds']:.3f}s | "
            f"Generation: {record['generation_seconds']}"
        )

    completed_at = utc_now()
    passed = sum(record["status"] == "passed" for record in results)
    total = len(results)

    all_prompt_tokens = [
        record["token_usage"]["prompt_tokens"]
        for record in results
        if record["token_usage"]["prompt_tokens"] is not None
    ]
    all_completion_tokens = [
        record["token_usage"]["completion_tokens"]
        for record in results
        if record["token_usage"]["completion_tokens"] is not None
    ]
    all_total_tokens = [
        record["token_usage"]["total_tokens"]
        for record in results
        if record["token_usage"]["total_tokens"] is not None
    ]

    status_counts = {}
    for record in results:
        status = record["status"]
        status_counts[status] = status_counts.get(status, 0) + 1

    output = {
        "run_id": run_id,
        "approach": "single_llm",
        "started_at_utc": started_at,
        "completed_at_utc": completed_at,
        "model_config": {
            "provider": "Ollama OpenAI-compatible API",
            "model": MODEL_NAME,
            "endpoint": OLLAMA_BASE_URL,
            "temperature": 0,
            "max_retries": 0,
            "llm_calls": sum(r["llm_calls"] for r in results),
        },
        "dataset": {
            "name": "custom_10_case_ci_failure_benchmark",
            "case_count": total,
            "case_ids": [record["case_id"] for record in results],
        },
        "cases": results,
        "summary": {
            "passed": passed,
            "total_cases": total,
            "pass_rate_percent": round(passed / total * 100, 2)
            if total else 0.0,
            "status_counts": status_counts,
            "total_elapsed_seconds": round(
                sum(r["elapsed_seconds"] or 0 for r in results), 6
            ),
            "total_generation_seconds": round(
                sum(r["generation_seconds"] or 0 for r in results), 6
            ),
            "token_usage": {
                "prompt_tokens": (
                    sum(all_prompt_tokens)
                    if len(all_prompt_tokens) == total else None
                ),
                "completion_tokens": (
                    sum(all_completion_tokens)
                    if len(all_completion_tokens) == total else None
                ),
                "total_tokens": (
                    sum(all_total_tokens)
                    if len(all_total_tokens) == total else None
                ),
                "cases_with_reported_usage": len(all_total_tokens),
            },
        },
        "limitations": [
            "One direct local LLM call per case; no retries or fallbacks.",
            "Each case starts from its original broken source.",
            "Token usage is null when the API does not report it.",
            "Elapsed time excludes process startup and model loading before the run.",
            "Generated code is evaluated only against trusted benchmark cases.",
        ],
    }

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = RUNS_ROOT / (
        f"single_llm_{timestamp}_{run_id[:8]}.json"
    )

    if output_path.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing run: {output_path}"
        )

    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")

    print("\n========== SINGLE-LLM SUMMARY ==========")
    print(f"Cases: {total}")
    print(f"Passed: {passed}")
    print(f"Pass rate: {output['summary']['pass_rate_percent']}%")
    print(
        "Generation time (seconds): "
        f"{output['summary']['total_generation_seconds']}"
    )
    print(f"Token usage: {output['summary']['token_usage']}")
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()
