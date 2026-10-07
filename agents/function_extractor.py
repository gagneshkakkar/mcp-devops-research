import ast
from pathlib import Path


def extract_function(
    file_path: str,
    function_name: str
) -> str:
    """
    Extract the exact source code of a Python function.
    """

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(
            f"File not found: {file_path}"
        )

    source = path.read_text(encoding="utf-8")

    tree = ast.parse(source)

    lines = source.splitlines()

    for node in ast.walk(tree):

        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef)
        ):

            if node.name == function_name:

                start = node.lineno - 1
                end = node.end_lineno

                return "\n".join(
                    lines[start:end]
                )

    raise ValueError(
        f"Function '{function_name}' not found in {file_path}"
    )


if __name__ == "__main__":

    result = extract_function(
        "app/calculator.py",
        "multiply"
    )

    print("========== EXTRACTED FUNCTION ==========")
    print(result)