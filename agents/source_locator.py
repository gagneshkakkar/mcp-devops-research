import ast
from pathlib import Path


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
    test_name: str | None = None
) -> list:
    """
    Extract implementation function calls from a test file.

    If test_name is supplied, only inspect that specific
    test function.
    """

    source = test_file.read_text(
        encoding="utf-8"
    )

    tree = ast.parse(source)

    functions = []

    target_node = None

    # --------------------------------------------------
    # Find the specific test function
    # --------------------------------------------------

    if test_name:

        for node in tree.body:

            if isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef)
            ):

                if node.name == test_name:

                    target_node = node
                    break

    # --------------------------------------------------
    # If no specific test was requested,
    # inspect the entire file.
    # --------------------------------------------------

    if target_node is None:

        target_node = tree

    # --------------------------------------------------
    # Find function calls
    # --------------------------------------------------

    for node in ast.walk(target_node):

        if isinstance(node, ast.Call):

            if isinstance(
                node.func,
                ast.Name
            ):

                functions.append(
                    node.func.id
                )

            elif isinstance(
                node.func,
                ast.Attribute
            ):

                functions.append(
                    node.func.attr
                )

    return list(
        dict.fromkeys(functions)
    )


def find_function_definition(function_name: str, root: str = "."):
    """
    Search the repository for the Python file containing
    the requested function definition.
    """

    root_path = Path(root)

    matches = []

    for file_path in root_path.rglob("*.py"):

        # Ignore virtual environment and cache files
        if ".venv" in file_path.parts:
            continue

        if "__pycache__" in file_path.parts:
            continue

        if ".backups" in file_path.parts:
            continue
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (UnicodeDecodeError, SyntaxError):
            continue

        for node in ast.walk(tree):

            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):

                if node.name == function_name:
                    matches.append(file_path)

    return matches

def read_source_file(file_path: Path) -> str:
    """
    Read a Python source file safely.
    """

    try:
        return file_path.read_text(encoding="utf-8")
    except (FileNotFoundError, UnicodeDecodeError) as e:
        return f"Unable to read {file_path}: {e}"

if __name__ == "__main__":

    failed_test = "tests/test_project.py::test_multiply"

    # --------------------------------------------------
    # 1. Locate test file
    # --------------------------------------------------

    test_file = find_test_file(failed_test)

    print("========== TEST FILE ==========")
    print(test_file)

    # --------------------------------------------------
    # 2. Find functions used by the test file
    # --------------------------------------------------

    functions = extract_test_functions(test_file)

    print("\n========== FUNCTIONS ==========")
    print(functions)

    # --------------------------------------------------
    # 3. Locate implementations
    # --------------------------------------------------

    print("\n========== IMPLEMENTATIONS ==========")

    implementation_files = []

    for function in functions:

        matches = find_function_definition(function)

        for match in matches:

            print(f"{function} -> {match}")

            if match not in implementation_files:
                implementation_files.append(match)

    # --------------------------------------------------
    # 4. Read test source
    # --------------------------------------------------

    test_source = read_source_file(test_file)

    print("\n========== TEST SOURCE ==========")
    print(test_source)

    # --------------------------------------------------
    # 5. Read implementation source
    # --------------------------------------------------

    print("\n========== IMPLEMENTATION SOURCE ==========")

    for file_path in implementation_files:

        print(f"\n--- {file_path} ---")

        source = read_source_file(file_path)

        print(source)