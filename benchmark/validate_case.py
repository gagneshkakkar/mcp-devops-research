
import json
import sys
from pathlib import Path


def execute_function(source_path: Path, function_name: str, inputs: dict):
    """Compile and execute a benchmark function, capturing errors."""
    namespace = {}

    try:
        source = source_path.read_text(encoding="utf-8")

        code = compile(
            source,
            str(source_path),
            "exec",
        )

        exec(code, namespace)

        function = namespace[function_name]

        return {
            "output": function(**inputs),
            "exception": None,
        }

    except Exception as error:
        return {
            "output": None,
            "exception": type(error).__name__,
        }


def validate_case(case_dir: Path) -> bool:
    metadata_path = case_dir / "metadata.json"
    broken_path = case_dir / "broken" / "calculator.py"
    expected_path = case_dir / "expected" / "calculator.py"

    metadata = json.loads(
        metadata_path.read_text(encoding="utf-8")
    )

    function_name = metadata["function"]
    inputs = metadata["input"]

    broken_result = execute_function(
        broken_path,
        function_name,
        inputs,
    )

    expected_result = execute_function(
        expected_path,
        function_name,
        inputs,
    )

    expected_exception = metadata.get("expected_exception")

    if expected_exception:
        broken_valid = (
            broken_result["exception"] == expected_exception
        )
    else:
        broken_valid = (
            broken_result["exception"] is None
            and broken_result["output"] == metadata["broken_output"]
        )

    expected_valid = (
        expected_result["exception"] is None
        and expected_result["output"] == metadata["expected_output"]
    )

    distinct = broken_result != expected_result

    valid = broken_valid and expected_valid and distinct

    print(
        f"\nBenchmark: {metadata['id']} — {metadata['title']}"
    )

    if broken_result["exception"]:
        print(f"Broken exception: {broken_result['exception']}")
    else:
        print(f"Broken output: {broken_result['output']}")

    print(f"Expected output: {metadata['expected_output']}")

    if expected_result["exception"]:
        print(f"Corrected exception: {expected_result['exception']}")
    else:
        print(f"Corrected output: {expected_result['output']}")

    print(f"Validation: {'PASSED' if valid else 'FAILED'}")

    if not valid:
        print(f"Broken result details: {broken_result}")
        print(f"Expected result details: {expected_result}")

    return valid


def main():
    benchmark_root = Path(__file__).parent / "failures"

    case_dirs = sorted(
        path
        for path in benchmark_root.iterdir()
        if path.is_dir() and (path / "metadata.json").exists()
    )

    if not case_dirs:
        print("No benchmark cases found.")
        sys.exit(1)

    results = [
        validate_case(case_dir)
        for case_dir in case_dirs
    ]

    passed = sum(results)
    failed = len(results) - passed

    print("\n========== BENCHMARK VALIDATION ==========")
    print(f"Total cases: {len(results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
