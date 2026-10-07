import ast
from pathlib import Path
from datetime import datetime


# ============================================================
# FUNCTION SOURCE
# ============================================================

def find_function_source(
    source: str,
    function_name: str
) -> tuple[int, int]:
    """
    Find the start and end line numbers of a function.
    """

    tree = ast.parse(source)

    for node in ast.walk(tree):

        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef)
        ):

            if node.name == function_name:

                return (
                    node.lineno - 1,
                    node.end_lineno
                )

    raise ValueError(
        f"Function '{function_name}' not found."
    )


# ============================================================
# BACKUP CREATION
# ============================================================

def create_backup(
    target: Path
) -> Path:
    """
    Create a unique backup of the target file.

    Backups are stored inside:

        .backups/

    A timestamp is included so multiple repairs cannot
    overwrite each other's backups.
    """

    backup_directory = (
        target.parent.parent
        / ".backups"
    )

    backup_directory.mkdir(
        parents=True,
        exist_ok=True
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S_%f"
    )

    backup_name = (
        f"{target.stem}_"
        f"{timestamp}"
        f"{target.suffix}"
    )

    backup_path = (
        backup_directory
        / backup_name
    )

    source = target.read_text(
        encoding="utf-8"
    )

    backup_path.write_text(
        source,
        encoding="utf-8"
    )

    return backup_path


# ============================================================
# APPLY REPAIR
# ============================================================

def apply_repair(
    file_path: str,
    function_name: str,
    old_code: str,
    new_code: str
) -> dict:
    """
    Safely apply a repair inside a specific function.

    A unique backup is created BEFORE modifying the file.
    """

    target = Path(
        file_path
    )

    # --------------------------------------------------------
    # 1. Check target file
    # --------------------------------------------------------

    if not target.exists():

        return {
            "success": False,
            "message": (
                f"File does not exist: "
                f"{file_path}"
            )
        }

    # --------------------------------------------------------
    # 2. Read source
    # --------------------------------------------------------

    try:

        source = target.read_text(
            encoding="utf-8"
        )

    except Exception as error:

        return {
            "success": False,
            "message": (
                f"Unable to read file: "
                f"{error}"
            )
        }

    # --------------------------------------------------------
    # 3. Locate target function
    # --------------------------------------------------------

    try:

        start, end = find_function_source(
            source,
            function_name
        )

    except ValueError as error:

        return {
            "success": False,
            "message": str(error)
        }

    # --------------------------------------------------------
    # 4. Extract function source
    # --------------------------------------------------------

    lines = source.splitlines(
        keepends=True
    )

    function_source = "".join(
        lines[start:end]
    )

    # --------------------------------------------------------
    # 5. Check old code inside function only
    # --------------------------------------------------------

    occurrence_count = (
        function_source.count(
            old_code
        )
    )

    if occurrence_count == 0:

        return {
            "success": False,
            "message": (
                "Original code was not found "
                f"inside function "
                f"'{function_name}'."
            )
        }

    if occurrence_count > 1:

        return {
            "success": False,
            "message": (
                "Repair rejected: original code "
                f"occurs {occurrence_count} times "
                f"inside function "
                f"'{function_name}'."
            )
        }

    # --------------------------------------------------------
    # 6. Validate that replacement is different
    # --------------------------------------------------------

    if old_code == new_code:

        return {
            "success": False,
            "message": (
                "Repair rejected: old_code and "
                "new_code are identical."
            )
        }

    # --------------------------------------------------------
    # 7. Create unique backup
    # --------------------------------------------------------

    try:

        backup_path = create_backup(
            target
        )

    except Exception as error:

        return {
            "success": False,
            "message": (
                f"Unable to create backup: "
                f"{error}"
            )
        }

    # --------------------------------------------------------
    # 8. Apply replacement only inside function
    # --------------------------------------------------------

    repaired_function = (
        function_source.replace(
            old_code,
            new_code,
            1
        )
    )

    repaired_source = (
        "".join(lines[:start])
        + repaired_function
        + "".join(lines[end:])
    )

    # --------------------------------------------------------
    # 9. Validate resulting Python syntax
    # --------------------------------------------------------

    try:

        ast.parse(
            repaired_source
        )

    except SyntaxError as error:

        # Restore original file immediately.

        target.write_text(
            source,
            encoding="utf-8"
        )

        return {
            "success": False,
            "message": (
                "Repair rejected because the "
                f"resulting source contains a "
                f"syntax error: {error}"
            ),
            "backup": str(
                backup_path
            )
        }

    # --------------------------------------------------------
    # 10. Write repaired source
    # --------------------------------------------------------

    try:

        target.write_text(
            repaired_source,
            encoding="utf-8"
        )

    except Exception as error:

        # Restore original source if writing fails.

        target.write_text(
            source,
            encoding="utf-8"
        )

        return {
            "success": False,
            "message": (
                f"Unable to write repaired "
                f"file: {error}"
            ),
            "backup": str(
                backup_path
            )
        }

    # --------------------------------------------------------
    # 11. Return repair metadata
    # --------------------------------------------------------

    return {
        "success": True,
        "message": (
            "Repair applied successfully."
        ),
        "file": str(
            target
        ),
        "function": function_name,
        "backup": str(
            backup_path
        ),
        "old_code": old_code,
        "new_code": new_code
    }


# ============================================================
# STANDALONE TEST
# ============================================================

if __name__ == "__main__":

    repair = {
        "file": "app/calculator.py",
        "function": "multiply",
        "old_code": "return a + b",
        "new_code": "return a * b"
    }

    result = apply_repair(
        file_path=repair["file"],
        function_name=repair["function"],
        old_code=repair["old_code"],
        new_code=repair["new_code"]
    )

    print(
        "========== REPAIR APPLICATION =========="
    )

    for key, value in result.items():

        print(
            f"{key}: {value}"
        )