import json
import re
import shutil
import traceback
from pathlib import Path

from openai import OpenAI


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_ROOT = PROJECT_ROOT / "benchmark" / "failures"

WORKSPACES_ROOT = (
    PROJECT_ROOT
    / "benchmark"
    / "baseline_workspaces"
    / "single_llm"
)

RESULTS_PATH = (
    PROJECT_ROOT
    / "benchmark"
    / "results"
    / "baseline_single_llm_results.json"
)

MODEL_NAME = "qwen2.5-coder:7b"
OLLAMA_BASE_URL = "http://localhost:11434/v1"

client = OpenAI(
    base_url=OLLAMA_BASE_URL,
    api_key="ollama",
    timeout=180.0,
    max_retries=0,
)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8",
    )


def prepare_workspace(case_id):
    source_path = (
        BENCHMARK_ROOT
        / case_id
        / "broken"
        / "calculator.py"
    )

    workspace_path = (
        WORKSPACES_ROOT
        / case_id
        / "calculator.py"
    )

    if not source_path.is_file():
        raise FileNotFoundError(
            f"Broken source missing: {source_path}"
        )

    workspace_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Always reset the workspace from the original broken source.
    shutil.copy2(source_path, workspace_path)

    return workspace_path


def clean_model_response(content):
    if not content:
        raise ValueError("The model returned an empty response.")

    content = content.strip()

    # Remove a Markdown code fence if the model includes one.
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

    # Reject explanations instead of silently treating them as code.
    if not content:
        raise ValueError("No Python source remained after cleaning.")

    return content + "\n"


def generate_repair(case_id, title, function_name, source):
    prompt = f"""
You are a Python code repair model.

Repair the supplied broken Python file.

Benchmark case: {case_id}
Failure description: {title}
Target function: {function_name}

Rules:
1. Return the COMPLETE corrected Python file.
2. Return Python source code only. Do not use Markdown fences.
3. Do not include explanations outside the source code.
4. Preserve unrelated functions and behavior.
5. Do not modify tests or benchmark metadata.
6. Do not use hardcoded answers for the test input.
7. Do not install packages or access the network.
8. Fix the underlying defect, not just its symptoms.
9. You may fix syntax errors, imports, function logic,
   dependency usage, runtime errors, and configuration handling.
10. Do not assume the expected test output.

Broken Python file:
--------------------
{source}
--------------------

Return the complete corrected Python file now.
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        temperature=0,
    )

    content = response.choices[0].message.content
    return clean_model_response(content)


def evaluate_behavior(source_path, metadata):
    source = source_path.read_text(encoding="utf-8")

    # Compilation catches syntax errors before execution.
    compiled = compile(
        source,
        str(source_path),
        "exec",
    )

    namespace = {
        "__name__": "single_llm_benchmark",
    }

    exec(compiled, namespace)

    function_name = metadata["function"]

    if function_name not in namespace:
        raise ValueError(
            f"Function {function_name!r} was not found "
            "in the repaired file."
        )

    function = namespace[function_name]
    actual = function(**metadata["input"])
    expected = metadata["expected_output"]

    return {
        "passed": actual == expected,
        "actual_output": actual,
        "expected_output": expected,
        "actual_exception": None,
    }


def main():
    if not client.models:
        raise RuntimeError("The model client is unavailable.")

    case_directories = sorted(
        path
        for path in BENCHMARK_ROOT.iterdir()
        if path.is_dir() and path.name.startswith("F")
    )

    results = {
        "experiment": "single_llm_baseline",
        "model": MODEL_NAME,
        "endpoint": OLLAMA_BASE_URL,
        "mode": "single_model_one_attempt",
        "total_cases": len(case_directories),
        "cases": [],
        "notes": [
            "Uses one direct local LLM repair-generation call per case.",
            "No multi-agent orchestration is used.",
            "No retries or rule-based repair fallbacks are used.",
            "Each case starts from its original broken source.",
            "The expected output is used only for evaluation, "
            "not included in the model prompt.",
            "Model-generated source is evaluated in a local "
            "benchmark workspace; use only trusted benchmark cases.",
        ],
    }

    for case_dir in case_directories:
        case_id = case_dir.name
        metadata = read_json(case_dir / "metadata.json")

        record = {
            "id": case_id,
            "title": metadata["title"],
            "status": "not_started",
            "repair_strategy": "single_llm_full_file",
            "repair_attempted": False,
            "repair_generated": False,
            "repair_applied": False,
            "tests_passed": False,
            "llm_calls": 0,
            "error": None,
        }

        print(
            f"\n========== {case_id}: "
            f"{metadata['title']} =========="
        )

        try:
            workspace_path = prepare_workspace(case_id)
            original_source = workspace_path.read_text(
                encoding="utf-8"
            )

            record["repair_attempted"] = True
            record["llm_calls"] = 1

            repaired_source = generate_repair(
                case_id=case_id,
                title=metadata["title"],
                function_name=metadata["function"],
                source=original_source,
            )

            record["repair_generated"] = True

            # Validate syntax before writing the repaired file.
            compile(
                repaired_source,
                str(workspace_path),
                "exec",
            )

            workspace_path.write_text(
                repaired_source,
                encoding="utf-8",
            )

            record["repair_applied"] = True

            behavior = evaluate_behavior(
                workspace_path,
                metadata,
            )

            record["behavior"] = behavior
            record["tests_passed"] = behavior["passed"]
            record["status"] = (
                "passed" if behavior["passed"]
                else "test_failed"
            )

            print("Actual output:", behavior["actual_output"])
            print("Expected output:", behavior["expected_output"])
            print("Outcome:", record["status"])

        except Exception as error:
            record["status"] = "error"
            record["error"] = (
                f"{type(error).__name__}: {error}"
            )

            print("Outcome: error")
            print("Details:", record["error"])
            traceback.print_exc()

        results["cases"].append(record)
        write_json(RESULTS_PATH, results)

    summary = {}

    for record in results["cases"]:
        status = record["status"]
        summary[status] = summary.get(status, 0) + 1

    passed = summary.get("passed", 0)
    total = len(results["cases"])

    results["summary"] = summary
    results["passed_cases"] = passed
    results["observed_pass_rate_percent"] = (
        round(passed / total * 100, 2)
        if total
        else 0
    )

    write_json(RESULTS_PATH, results)

    print("\n========== SINGLE-LLM BASELINE SUMMARY ==========")
    print(f"Cases recorded: {total}")

    for status, count in sorted(summary.items()):
        print(f"{status}: {count}")

    print(
        f"Observed pass rate: {passed / total * 100:.1f}%"
        if total
        else "No cases found."
    )
    print(f"Results saved to: {RESULTS_PATH}")


if __name__ == "__main__":
    main()