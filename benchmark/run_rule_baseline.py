
import ast
import json
import shutil
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_ROOT = PROJECT_ROOT / "benchmark" / "failures"
WORKSPACES_ROOT = PROJECT_ROOT / "benchmark" / "baseline_workspaces" / "rule"
RESULTS_ROOT = PROJECT_ROOT / "benchmark" / "results"

RESULTS_PATH = RESULTS_ROOT / "baseline_rule_results.json"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def prepare_workspace(case_id):
    source_path = BENCHMARK_ROOT / case_id / "broken" / "calculator.py"
    workspace_path = WORKSPACES_ROOT / case_id / "calculator.py"

    source_path.resolve().relative_to(BENCHMARK_ROOT.resolve())
    workspace_path.resolve().relative_to(WORKSPACES_ROOT.resolve())

    if not source_path.is_file():
        raise FileNotFoundError(f"Broken source missing: {source_path}")

    workspace_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, workspace_path)

    return workspace_path


def get_function_node(source, function_name):
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == function_name:
                return node

    return None


def replace_function_body(source, function_name, new_body):
    """
    Replace the body of a named function while preserving its signature.
    The original source must parse successfully.
    """
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)

    function_node = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == function_name:
                function_node = node
                break

    if function_node is None:
        raise ValueError(f"Function {function_name} not found.")

    body_start = function_node.body[0].lineno - 1
    body_end = function_node.end_lineno

    indent = " " * (function_node.col_offset + 4)
    replacement = "".join(
        indent + line + "\n" for line in new_body.splitlines()
    )

    updated_lines = lines[:body_start] + [replacement] + lines[body_end:]
    updated = "".join(updated_lines)

    compile(updated, "<rule-baseline>", "exec")
    return updated


def apply_rule(case_id, source, metadata):
    """
    Apply a predefined, deterministic rule for this benchmark case.

    These rules are specific to the supplied benchmark. F06 is unsupported
    because this baseline intentionally does not repair syntax errors.
    """
    function_name = metadata["function"]

    if case_id == "F01":
        old = "return a + b"
        new = "return a * b"
        if source.count(old) != 1:
            return None, "Expected multiplication bug pattern not found."
        return source.replace(old, new, 1), "Applied multiplication rule."

    if case_id == "F02":
        old = "return a * b"
        new = "return a / b"
        if source.count(old) != 1:
            return None, "Expected division bug pattern not found."
        return source.replace(old, new, 1), "Applied division rule."

    if case_id == "F03":
        old = "return result"
        new = "return a + b"
        if source.count(old) != 1:
            return None, "Expected undefined-variable pattern not found."
        return source.replace(old, new, 1), "Applied undefined-variable rule."

    if case_id == "F04":
        old = "calculate_summ"
        new = "calculate_sum"
        if source.count(old) != 1:
            return None, "Expected misspelled function reference not found."
        return source.replace(old, new, 1), "Applied function-name rule."

    if case_id == "F05":
        if "import math" in source.splitlines():
            return None, "math import already exists."
        updated = "import math\n" + source
        compile(updated, "<rule-baseline>", "exec")
        return updated, "Added the standard-library math import."

    if case_id == "F06":
        return None, "Syntax-error repair is unsupported by this baseline."

    if case_id == "F07":
        old = "return number % 2 == 1"
        new = "return number % 2 == 0"
        if source.count(old) != 1:
            return None, "Expected parity-check pattern not found."
        return source.replace(old, new, 1), "Applied even-number rule."

    if case_id == "F08":
        old = "return benchmark_missing_package.double(value)"
        new = "return value * 2"
        if source.count(old) != 1:
            return None, "Expected missing-dependency call not found."

        updated = source.replace(old, new, 1)
        updated_lines = [
            line for line in updated.splitlines(keepends=True)
            if line.strip() != "import benchmark_missing_package"
        ]
        updated = "".join(updated_lines)
        compile(updated, "<rule-baseline>", "exec")
        return updated, "Replaced missing dependency and removed its import."

    if case_id == "F09":
        tree = ast.parse(source)
        lines = source.splitlines(keepends=True)
        function_node = get_function_node(source, function_name)

        if function_node is None:
            return None, "Runtime-label function not found."

        target_if = None
        for node in ast.walk(function_node):
            if isinstance(node, ast.If):
                has_runtime_error = any(
                    isinstance(child, ast.Raise)
                    and isinstance(child.exc, ast.Call)
                    and isinstance(child.exc.func, ast.Name)
                    and child.exc.func.id == "RuntimeError"
                    for child in ast.walk(node)
                )
                if has_runtime_error:
                    target_if = node
                    break

        if target_if is None:
            return None, "Simulated runtime incompatibility block not found."

        del lines[target_if.lineno - 1:target_if.end_lineno]
        updated = "".join(lines)
        compile(updated, "<rule-baseline>", "exec")
        return updated, "Removed simulated runtime incompatibility block."

    if case_id == "F10":
        old = 'return os.environ["BENCHMARK_API_URL"]'
        new = 'return os.environ.get("BENCHMARK_API_URL", "https://example.test/api")'
        if source.count(old) != 1:
            return None, "Expected environment-variable lookup not found."
        return source.replace(old, new, 1), "Added default URL handling."

    return None, f"No rule defined for {case_id}."


def evaluate(source_path, metadata):
    source = source_path.read_text(encoding="utf-8")
    namespace = {}

    exec(compile(source, str(source_path), "exec"), namespace)
    function = namespace[metadata["function"]]

    try:
        actual = function(**metadata["input"])
    except Exception as error:
        return {
            "passed": False,
            "actual_output": None,
            "actual_exception": type(error).__name__,
            "expected_output": metadata["expected_output"],
        }

    return {
        "passed": actual == metadata["expected_output"],
        "actual_output": actual,
        "actual_exception": None,
        "expected_output": metadata["expected_output"],
    }


def main():
    case_directories = sorted(
        path for path in BENCHMARK_ROOT.iterdir()
        if path.is_dir() and path.name.startswith("F")
    )

    results = {
        "experiment": "benchmark_specific_rule_based_baseline",
        "mode": "isolated_rule_based",
        "total_cases": len(case_directories),
        "cases": [],
        "notes": [
            "Rules are specifically written for this 10-case benchmark.",
            "No LLM calls are made.",
            "F06 syntax-error repair is intentionally unsupported.",
            "This result must not be described as a general-purpose baseline.",
        ],
    }

    for case_dir in case_directories:
        case_id = case_dir.name
        metadata_path = case_dir / "metadata.json"
        metadata = read_json(metadata_path)

        record = {
            "id": case_id,
            "title": metadata["title"],
            "status": "not_started",
            "repair_strategy": "predefined_rule",
            "repair_attempted": True,
            "repair_applied": False,
            "tests_passed": False,
            "error": None,
        }

        print(f"\n========== {case_id}: {metadata['title']} ==========")

        try:
            workspace_path = prepare_workspace(case_id)
            source = workspace_path.read_text(encoding="utf-8")

            try:
                compile(source, str(workspace_path), "exec")
            except SyntaxError as error:
                record["status"] = "unsupported_syntax_error"
                record["error"] = str(error)
                print("Unsupported: original source has a syntax error.")
                results["cases"].append(record)
                write_json(RESULTS_PATH, results)
                continue

            repaired_source, message = apply_rule(
                case_id, source, metadata
            )
            record["rule_message"] = message

            if repaired_source is None:
                record["status"] = "unsupported" if case_id == "F06" else "repair_failed"
                record["error"] = message
                print("Rule not applied:", message)
                results["cases"].append(record)
                write_json(RESULTS_PATH, results)
                continue

            compile(repaired_source, str(workspace_path), "exec")
            workspace_path.write_text(repaired_source, encoding="utf-8")
            record["repair_applied"] = True

            behavior = evaluate(workspace_path, metadata)
            record["behavior"] = behavior
            record["tests_passed"] = behavior["passed"]
            record["status"] = "passed" if behavior["passed"] else "test_failed"

            print("Actual output:", behavior["actual_output"])
            print("Expected output:", behavior["expected_output"])
            print("Outcome:", record["status"])

        except Exception as error:
            record["status"] = "error"
            record["error"] = f"{type(error).__name__}: {error}"
            print("Error:", record["error"])
            traceback.print_exc()

        results["cases"].append(record)
        write_json(RESULTS_PATH, results)

    summary = {}
    for record in results["cases"]:
        status = record["status"]
        summary[status] = summary.get(status, 0) + 1

    results["summary"] = summary
    write_json(RESULTS_PATH, results)

    passed = summary.get("passed", 0)
    total = len(results["cases"])

    print("\n========== RULE-BASED BASELINE SUMMARY ==========")
    print(f"Cases recorded: {total}")
    for status, count in sorted(summary.items()):
        print(f"{status}: {count}")
    print(f"Observed pass rate: {passed / total * 100:.1f}%" if total else "No cases.")
    print(f"Results saved to: {RESULTS_PATH}")


if __name__ == "__main__":
    main()
