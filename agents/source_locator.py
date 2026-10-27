
import ast
from pathlib import Path

try:
    from agents.import_resolver import resolve_imported_function
except ModuleNotFoundError as exc:
    if exc.name != "agents":
        raise
    from import_resolver import resolve_imported_function


def find_test_file(failed_test: str) -> Path:
    """
    Extract the test file path from a pytest failure identifier.

    Example:
        tests/test_project.py::test_multiply

    Returns:
        tests/test_project.py
    """
    test_path = failed_test.split("::")[0]
    return Path(test_path)


def extract_test_functions(
    test_file: Path,
    test_name: str | None = None,
) -> list[str]:
    """
    Extract function calls from a test file.

    If test_name is supplied, inspect only that test function.
    Otherwise, inspect the entire file.
    """
    try:
        source = test_file.read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
    except (OSError, UnicodeDecodeError, SyntaxError):
        return []

    target_node = None

    if test_name:
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == test_name:
                    target_node = node
                    break

        # Do not accidentally inspect the entire file if the
        # requested test function cannot be found.
        if target_node is None:
            return []

    if target_node is None:
        target_node = tree

    functions = []

    for node in ast.walk(target_node):
        if not isinstance(node, ast.Call):
            continue

        if isinstance(node.func, ast.Name):
            functions.append(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            functions.append(node.func.attr)

    return list(dict.fromkeys(functions))


def find_function_definition(
    function_name: str,
    root: str = ".",
    test_file: str = "tests/test_project.py",
) -> list[Path]:
    """
    Resolve a function through explicit imports in the test module.

    Unlike a repository-wide name search, this does not treat every
    matching function in benchmark fixtures as a repair target.

    Returns an empty list when the import cannot be resolved
    confidently.
    """
    return resolve_imported_function(
        test_file=test_file,
        function_name=function_name,
        root=root,
    )


def read_source_file(file_path: Path) -> str:
    """Read a source file safely."""
    try:
        return file_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as error:
        return f"Unable to read {file_path}: {error}"


if __name__ == "__main__":
    failed_test = "tests/test_project.py::test_multiply"

    # 1. Locate the test file and specific test function.
    test_file = find_test_file(failed_test)
    test_name = failed_test.split("::")[-1]

    print("========== TEST FILE ==========")
    print(test_file)

    if not test_file.is_file():
        raise SystemExit(f"Test file not found: {test_file}")

    # 2. Extract function calls from the requested test only.
    functions = extract_test_functions(
        test_file,
        test_name,
    )

    print("\n========== FUNCTIONS ==========")
    print(functions)

    # 3. Resolve functions through imports in this test module.
    print("\n========== IMPLEMENTATIONS ==========")

    implementation_files = []

    for function in functions:
        matches = find_function_definition(
            function_name=function,
            test_file=str(test_file),
        )

        if not matches:
            print(f"{function} -> unresolved; no target selected")
            continue

        for match in matches:
            print(f"{function} -> {match}")

            if match not in implementation_files:
                implementation_files.append(match)

    # 4. Display the test source.
    print("\n========== TEST SOURCE ==========")
    print(read_source_file(test_file))

    # 5. Display only resolved implementation sources.
    print("\n========== IMPLEMENTATION SOURCE ==========")

    for file_path in implementation_files:
        print(f"\n--- {file_path} ---")
        print(read_source_file(file_path))
