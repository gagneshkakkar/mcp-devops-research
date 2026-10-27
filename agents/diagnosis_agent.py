import ast
import json
import operator
import os
import re
from pathlib import Path

from openai import OpenAI

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from agents.import_resolver import resolve_imported_function

# ============================================================
# Ollama / Local LLM
# ============================================================

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"
)


# ============================================================
# MCP SERVER CONFIGURATION
# ============================================================

server_params = StdioServerParameters(
    command="python",
    args=[
        "-m",
        "mcp_server.server"
    ],
    env=os.environ.copy(),
)


# ============================================================
# LLM
# ============================================================

def ask_llm(prompt: str) -> dict:
    """
    Ask the local LLM for a structured diagnosis.
    """

    response = client.chat.completions.create(
        model="qwen2.5-coder:7b",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    content = response.choices[0].message.content.strip()

    # --------------------------------------------------------
    # Remove markdown code fences
    # --------------------------------------------------------

    if content.startswith("```"):

        lines = content.splitlines()

        if lines and lines[0].startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        content = "\n".join(lines).strip()

    # --------------------------------------------------------
    # Parse JSON
    # --------------------------------------------------------

    try:

        return json.loads(content)

    except json.JSONDecodeError:

        # ----------------------------------------------------
        # Repair common invalid Windows-path escaping
        # ----------------------------------------------------

        repaired_content = ""

        i = 0

        while i < len(content):

            character = content[i]

            if character == "\\":

                if i + 1 < len(content):

                    next_character = content[i + 1]

                    valid_escapes = (
                        '"',
                        "\\",
                        "/",
                        "b",
                        "f",
                        "n",
                        "r",
                        "t",
                        "u",
                    )

                    if next_character in valid_escapes:
                        repaired_content += "\\"
                    else:
                        repaired_content += "\\\\"

                else:
                    repaired_content += "\\\\"

            else:
                repaired_content += character

            i += 1

        try:

            return json.loads(
                repaired_content
            )

        except json.JSONDecodeError as error:

            print(
                "\n========== RAW LLM RESPONSE =========="
            )

            print(content)

            raise ValueError(
                "LLM returned invalid JSON "
                f"after repair attempt: {error}"
            )


def extract_commit_sha(status_text: str) -> str:
    """Extract a full 40-character Git commit SHA from MCP build status."""
    match = re.search(
        r"(?m)^Commit SHA:\s*([0-9a-fA-F]{40})\s*$",
        status_text,
    )
    if not match:
        raise ValueError(
            "Build status is missing a valid 40-character Commit SHA; "
            "historical-source diagnosis cannot continue safely."
        )
    return match.group(1).lower()


# ============================================================
# TEST NAME NORMALIZATION
# ============================================================

def normalize_test_name(
    test_name: str,
    known_tests: list[str]
) -> str | None:
    """
    Convert different LLM representations of a pytest test
    into the authoritative pytest node ID.

    Examples:

        test_multiply
        tests/test_project.py::test_multiply

    both become:

        tests/test_project.py::test_multiply
    """

    if not test_name:
        return None

    value = str(
        test_name
    ).strip()

    value = value.strip(
        "`"
    )

    # --------------------------------------------------------
    # Exact match
    # --------------------------------------------------------

    if value in known_tests:
        return value

    # --------------------------------------------------------
    # Remove pytest node-id prefixes
    # --------------------------------------------------------

    short_name = value.split(
        "::"
    )[-1]

    # --------------------------------------------------------
    # Compare against authoritative tests
    # --------------------------------------------------------

    matches = []

    for known_test in known_tests:

        known_short_name = known_test.split(
            "::"
        )[-1]

        if short_name == known_short_name:
            matches.append(
                known_test
            )

    # --------------------------------------------------------
    # Only accept an unambiguous match
    # --------------------------------------------------------

    if len(matches) == 1:
        return matches[0]

    return None


# ============================================================
# DIAGNOSIS STRUCTURE VALIDATION
# ============================================================

def validate_diagnosis_structure(
    diagnosis: dict
) -> None:
    """
    Validate the basic structure returned by the LLM.
    """

    if not isinstance(
        diagnosis,
        dict
    ):
        raise ValueError(
            "LLM diagnosis must be a JSON object."
        )

    if "diagnoses" not in diagnosis:

        raise ValueError(
            "LLM response is missing 'diagnoses'."
        )

    if not isinstance(
        diagnosis["diagnoses"],
        list
    ):

        raise ValueError(
            "'diagnoses' must be a list."
        )

    required_fields = [
        "test",
        "actual",
        "expected",
        "root_cause",
        "file",
        "function",
        "recommended_fix",
    ]

    for index, item in enumerate(
        diagnosis["diagnoses"],
        start=1
    ):

        if not isinstance(
            item,
            dict
        ):

            raise ValueError(
                f"Diagnosis {index} is not an object."
            )

        for field in required_fields:

            if field not in item:

                raise ValueError(
                    f"Diagnosis {index} is missing "
                    f"required field '{field}'."
                )


# ============================================================
# AUTHORITATIVE TARGET VALIDATION
# ============================================================

def validate_diagnosis_targets(
    diagnosis: dict,
    failure_contexts: list
) -> dict:
    """
    Validate LLM diagnoses against deterministic AST/source
    analysis.

    The LLM is NOT trusted to determine the implementation
    target.

    The authoritative target comes from source analysis.
    """

    validate_diagnosis_structure(
        diagnosis
    )

    diagnoses = diagnosis[
        "diagnoses"
    ]

    # --------------------------------------------------------
    # Build authoritative target map
    # --------------------------------------------------------

    expected_targets = {}

    for failure in failure_contexts:

        test_name = failure[
            "test"
        ]

        expected_files = []

        expected_functions = []

        for target in failure.get(
            "implementation_targets",
            []
        ):

            file_path = target[
                "file"
            ]

            function_name = target[
                "function"
            ]

            normalized_file = (
                file_path
                .replace(
                    "\\",
                    "/"
                )
            )

            expected_files.append(
                normalized_file
            )

            expected_functions.append(
                function_name
            )

        expected_targets[
            test_name
        ] = {
            "files": expected_files,
            "functions": expected_functions,
        }

    # --------------------------------------------------------
    # Normalize LLM test names
    # --------------------------------------------------------

    known_tests = list(
        expected_targets.keys()
    )

    normalized_diagnoses = []

    for index, item in enumerate(
        diagnoses,
        start=1
    ):

        original_test = item[
            "test"
        ]

        normalized_test = normalize_test_name(
            original_test,
            known_tests
        )

        if normalized_test is None:

            raise ValueError(
                f"Diagnosis {index} refers to an "
                f"unknown or ambiguous failed test: "
                f"{original_test}"
            )

        # Keep the authoritative test name.
        item["test"] = normalized_test

        normalized_diagnoses.append(
            item
        )

    diagnosis[
        "diagnoses"
    ] = normalized_diagnoses

    diagnoses = normalized_diagnoses

    # --------------------------------------------------------
    # Make sure every failure has a diagnosis
    # --------------------------------------------------------

    expected_tests = set(
        expected_targets.keys()
    )

    diagnosed_tests = set(
        item["test"]
        for item in diagnoses
    )

    missing_tests = (
        expected_tests
        - diagnosed_tests
    )

    if missing_tests:

        raise ValueError(
            "LLM failed to diagnose: "
            + ", ".join(
                sorted(
                    missing_tests
                )
            )
        )

    # --------------------------------------------------------
    # Reject duplicate diagnoses
    # --------------------------------------------------------

    if len(
        diagnosed_tests
    ) != len(
        diagnoses
    ):

        raise ValueError(
            "LLM returned duplicate diagnoses "
            "for the same test."
        )

    # --------------------------------------------------------
    # Validate every diagnosis target
    # --------------------------------------------------------

    for index, item in enumerate(
        diagnoses,
        start=1
    ):

        test_name = item[
            "test"
        ]

        if test_name not in expected_targets:

            raise ValueError(
                f"Diagnosis {index} refers to "
                f"unknown failed test: "
                f"{test_name}"
            )

        expected = expected_targets[
            test_name
        ]

        # ----------------------------------------------------
        # Normalize LLM file path
        # ----------------------------------------------------

        llm_file = (
            item["file"]
            .replace(
                "\\",
                "/"
            )
            .strip()
            .strip("`")
        )

        item["file"] = llm_file

        # ----------------------------------------------------
        # Normalize function
        # ----------------------------------------------------

        llm_function = (
            str(
                item["function"]
            )
            .strip()
            .strip("`")
        )

        item["function"] = (
            llm_function
        )

        # ----------------------------------------------------
        # File validation
        # ----------------------------------------------------

        if llm_file not in expected[
            "files"
        ]:

            raise ValueError(
                f"Diagnosis {index} target rejected.\n"
                f"Test: {test_name}\n"
                f"LLM file: {llm_file}\n"
                f"Expected implementation files: "
                f"{expected['files']}"
            )

        # ----------------------------------------------------
        # Function validation
        # ----------------------------------------------------

        if llm_function not in expected[
            "functions"
        ]:

            raise ValueError(
                f"Diagnosis {index} target rejected.\n"
                f"Test: {test_name}\n"
                f"LLM function: {llm_function}\n"
                f"Expected implementation functions: "
                f"{expected['functions']}"
            )

    # Fail closed on missing or invalid review decisions.
    # READY_FOR_VALIDATION permits a repair attempt, not approval
    # of the proposed patch or its final correctness.
    allowed_statuses = {
        "READY_FOR_VALIDATION",
        "REVIEW_REQUIRED",
    }

    for item in diagnoses:
        status = item.get("review_status")

        if status not in allowed_statuses:
            item["review_status"] = "REVIEW_REQUIRED"
            continue

        # Multiple authoritative targets are ambiguous.
        # Require human review rather than trusting the LLM's choice.
        target_info = expected_targets.get(item["test"], {})
        target_files = set(target_info.get("files", []))
        target_functions = set(target_info.get("functions", []))

        if len(target_files) > 1 or len(target_functions) > 1:
            item["review_status"] = "REVIEW_REQUIRED"

    return diagnosis


# ============================================================
# CONSERVATIVE SOURCE-EVIDENCE GATE
# ============================================================

def _literal_value(node):
    """Return a literal value, or None when the expression is not literal."""
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError):
        return None


def _evaluate_simple_expression(node, values):
    """
    Safely evaluate a small, side-effect-free subset of Python AST.
    Unsupported expressions return (False, None).
    """
    binary_ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }
    unary_ops = {
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
    }

    if isinstance(node, ast.Constant):
        return True, node.value

    if isinstance(node, ast.Name) and node.id in values:
        return True, values[node.id]

    if isinstance(node, ast.BinOp) and type(node.op) in binary_ops:
        left_ok, left = _evaluate_simple_expression(node.left, values)
        right_ok, right = _evaluate_simple_expression(node.right, values)
        if not left_ok or not right_ok:
            return False, None
        try:
            return True, binary_ops[type(node.op)](left, right)
        except (ArithmeticError, TypeError, ValueError, OverflowError):
            return False, None

    if isinstance(node, ast.UnaryOp) and type(node.op) in unary_ops:
        ok, value = _evaluate_simple_expression(node.operand, values)
        if not ok:
            return False, None
        try:
            return True, unary_ops[type(node.op)](value)
        except (ArithmeticError, TypeError, ValueError):
            return False, None

    return False, None


def _find_simple_test_call(test_source, function_name):
    """
    Find a simple assertion like `assert add(2, 3) == 6`.
    Returns (argument_values, expected_value) or None.
    """
    test_source = test_source.lstrip("\ufeff")
    try:
        tree = ast.parse(test_source)
    except (SyntaxError, TypeError):
        return None

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assert):
            continue
        test = node.test
        if not isinstance(test, ast.Compare) or len(test.ops) != 1:
            continue
        if not isinstance(test.ops[0], ast.Eq) or len(test.comparators) != 1:
            continue
        call = test.left
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
            continue
        if call.func.id != function_name:
            continue
        args = [_literal_value(arg) for arg in call.args]
        expected = _literal_value(test.comparators[0])
        if any(value is None for value in args) or expected is None:
            continue
        return args, expected
    return None


def apply_source_evidence_gate(
    diagnosis: dict,
    failure_contexts: list,
    implementation_source: dict,
) -> dict:
    """
    Conservatively downgrade diagnoses when simple source inspection shows
    that the implementation computes the reported actual value while the
    test expects another value. This does not prove a specification; it
    prevents an assertion mismatch alone from authorizing an automatic edit.
    """
    contexts_by_test = {
        context.get("test"): context
        for context in failure_contexts
        if context.get("test")
    }

    for item in diagnosis.get("diagnoses", []):
        if item.get("review_status") != "READY_FOR_VALIDATION":
            continue

        test_name = item.get("test")
        context = contexts_by_test.get(test_name)

        if not context:
            item["review_status"] = "REVIEW_REQUIRED"
            item["review_reason"] = "Missing failure context for source-evidence validation."
            continue

        targets = context.get("implementation_targets", [])
        matching_targets = [
            target for target in targets
            if target.get("file", "").replace("\\", "/") == item.get("file", "").replace("\\", "/")
            and target.get("function") == item.get("function")
        ]

        if len(targets) != 1 or len(matching_targets) != 1:
            item["review_status"] = "REVIEW_REQUIRED"
            item["review_reason"] = "Implementation target is missing or ambiguous."
            continue

        target_file = matching_targets[0].get("file", "")
        source = implementation_source.get(target_file, "")
        if not source.strip() or source.startswith("Unable to read "):
            item["review_status"] = "REVIEW_REQUIRED"
            item["review_reason"] = "Implementation source is unavailable."
            continue

        try:
            tree = ast.parse(source)
        except (SyntaxError, TypeError):
            item["review_status"] = "REVIEW_REQUIRED"
            item["review_reason"] = "Implementation source could not be parsed."
            continue

        function_node = next(
            (
                node for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == item.get("function")
            ),
            None,
        )
        if function_node is None:
            item["review_status"] = "REVIEW_REQUIRED"
            item["review_reason"] = "Target function was not found in supplied source."
            continue

        test_case = _find_simple_test_call(
            context.get("test_source", ""),
            item.get("function", ""),
        )
        if test_case is None:
            # The generic semantic relationship cannot be proven safely.
            item["review_status"] = "REVIEW_REQUIRED"
            item["review_reason"] = (
                "Could not independently evaluate a simple assertion against source."
            )
            continue

        arguments, expected_value = test_case
        positional_parameters = [
            arg.arg for arg in function_node.args.args
        ]
        if len(arguments) != len(positional_parameters):
            item["review_status"] = "REVIEW_REQUIRED"
            item["review_reason"] = "Test arguments do not match the target function signature."
            continue

        values = dict(zip(positional_parameters, arguments))
        returns = [
            node for node in ast.walk(function_node)
            if isinstance(node, ast.Return) and node.value is not None
        ]

        # Only a single, straightforward return expression is considered.
        if len(returns) != 1:
            item["review_status"] = "REVIEW_REQUIRED"
            item["review_reason"] = "Function control flow is too complex for the simple source checker."
            continue

        computed_ok, computed_value = _evaluate_simple_expression(
            returns[0].value, values
        )
        if not computed_ok:
            item["review_status"] = "REVIEW_REQUIRED"
            item["review_reason"] = "Source expression is outside the safe evaluator subset."
            continue

        actual_value = None
        try:
            actual_value = ast.literal_eval(str(item.get("actual", "")).strip())
        except (ValueError, TypeError, SyntaxError):
            actual_value = item.get("actual")

        if computed_value == actual_value and computed_value != expected_value:
            item["review_status"] = "REVIEW_REQUIRED"
            item["review_reason"] = (
                "Source computes the observed actual value; the assertion mismatch "
                "alone does not establish an implementation defect."
            )
        elif computed_value != expected_value:
            # The evaluator found a discrepancy but cannot infer intended behavior.
            item["review_status"] = "REVIEW_REQUIRED"
            item["review_reason"] = (
                "Source evaluation and test expectation differ; intended behavior "
                "requires independent confirmation."
            )

    return diagnosis


# ============================================================
# DIAGNOSIS TARGET EXTRACTION
# ============================================================

def find_test_file(
    failed_test: str
) -> Path:

    test_path = failed_test.split(
        "::"
    )[0]

    return Path(
        test_path
    )


def find_test_function(
    failed_test: str
) -> str:

    return failed_test.split(
        "::"
    )[-1]


# ============================================================
# READ FILE
# ============================================================

def read_file(
    file_path: Path
) -> str:

    try:

        return file_path.read_text(
            encoding="utf-8"
        )

    except Exception as error:

        return (
            f"Unable to read "
            f"{file_path}: {error}"
        )


# ============================================================
# FIND IMPLEMENTATION FUNCTIONS
# ============================================================

def find_function_definition(
    function_name: str,
    root: str = "."
) -> list[Path]:

    root_path = Path(
        root
    )

    matches = []

    for file_path in root_path.rglob(
        "*.py"
    ):

        if ".venv" in file_path.parts:
            continue

        if "__pycache__" in file_path.parts:
            continue

        if ".backups" in file_path.parts:
            continue

        try:

            source = file_path.read_text(
                encoding="utf-8"
            )

        except (
            UnicodeDecodeError,
            OSError
        ):

            continue

        try:

            import ast

            tree = ast.parse(
                source
            )

        except SyntaxError:

            continue

        for node in ast.walk(
            tree
        ):

            if isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef
                )
            ):

                if node.name == function_name:

                    matches.append(
                        file_path
                    )

    return matches


# ============================================================
# EXTRACT IMPLEMENTATION TARGETS
# ============================================================

def locate_implementation_targets(
    failed_test: str
) -> list[dict]:
    """
    Resolve implementation targets from explicit imports in the
    failed test file. Never guess based on repository-wide names.
    """
    test_file = find_test_file(failed_test)
    test_function = find_test_function(failed_test)

    if not test_file.exists():
        return []

    try:
        source = test_file.read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []

    target_node = next(
        (
            node for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == test_function
        ),
        None,
    )

    if target_node is None:
        return []

    called_functions = []
    for node in ast.walk(target_node):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called_functions.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called_functions.append(node.func.attr)

    targets = []
    seen = set()

    for function_name in dict.fromkeys(called_functions):
        resolved_files = resolve_imported_function(
            test_file,
            function_name,
        )

        for file_path in resolved_files:
            target = {
                "file": file_path.relative_to(Path.cwd()).as_posix(),
                "function": function_name,
            }
            key = (target["file"], target["function"])
            if key not in seen:
                seen.add(key)
                targets.append(target)

    return targets


# ============================================================
# DIAGNOSIS
# ============================================================

async def fetch_historical_source(
    client_session,
    path: str,
    commit_sha: str,
) -> str:
    """Fetch source from the exact failed CI commit; never use local fallback."""
    result = await client_session.call_tool(
        "get_repository_file_tool",
        {"path": path, "ref": commit_sha},
    )

    if getattr(result, "isError", False):
        raise RuntimeError("Historical source retrieval failed.")

    content = getattr(result, "content", None)
    if not content:
        raise RuntimeError("Historical source response was empty.")

    text = getattr(content[0], "text", "")
    if not text.strip():
        raise RuntimeError("Historical source response was empty.")

    if text.startswith("REPOSITORY_FILE_NOT_FOUND:"):
        raise FileNotFoundError(f"Historical file not found: {path}")

    if text.startswith((
        "REPOSITORY_FILE_HTTP_ERROR:",
        "REPOSITORY_FILE_RETRIEVAL_ERROR:",
        "Error retrieving repository file",
    )):
        raise RuntimeError("Historical source retrieval failed.")

    return text


async def locate_historical_implementation_targets(
    client_session,
    failed_test: str,
    test_source: str,
    commit_sha: str,
) -> list[dict]:
    """Resolve implementation targets using test source from the failed commit."""
    from agents.import_resolver import resolve_imported_function_from_source

    test_function = find_test_function(failed_test)

    try:
        tree = ast.parse(test_source.lstrip("\ufeff"))
    except (SyntaxError, TypeError):
        raise RuntimeError("Historical test source could not be parsed.")

    target_node = next(
        (
            node for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == test_function
        ),
        None,
    )

    if target_node is None:
        raise RuntimeError(
            f"Historical test function not found: {test_function}"
        )

    called_functions = []
    for node in ast.walk(target_node):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called_functions.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called_functions.append(node.func.attr)

    targets = []
    seen = set()

    for function_name in dict.fromkeys(called_functions):
        candidates = resolve_imported_function_from_source(
            test_source,
            function_name,
        )

        if not candidates:
            continue

        found = []
        for candidate in candidates:
            try:
                await fetch_historical_source(
                    client_session,
                    candidate,
                    commit_sha,
                )
                found.append(candidate)
            except FileNotFoundError:
                # Only a confirmed HTTP 404 means this candidate is absent.
                continue

        if len(found) > 1:
            raise RuntimeError(
                f"Ambiguous historical implementation for {function_name}."
            )

        if len(found) == 1:
            key = (found[0], function_name)
            if key not in seen:
                seen.add(key)
                targets.append({
                    "file": found[0],
                    "function": function_name,
                })

    if not targets:
        raise RuntimeError(
            f"No unambiguous historical implementation target found for {failed_test}."
        )

    return targets


async def diagnose_run(
    run_id: int | None = None
) -> dict:

    async with stdio_client(
        server_params
    ) as (
        read_stream,
        write_stream
    ):

        async with ClientSession(
            read_stream,
            write_stream
        ) as client_session:

            print(
                "Connected to MCP server."
            )

            await client_session.initialize()

            # ------------------------------------------------
            # Get latest run
            # ------------------------------------------------

            if run_id is None:

                status_result = (
                    await client_session.call_tool(
                        "get_build_status"
                    )
                )

                status_text = (
                    status_result.content[0].text
                )

                print(
                    "\n========== LATEST CI RUN =========="
                )

                print(
                    status_text
                )

                match = re.search(
                    r"Run ID:\s*(\d+)",
                    status_text
                )

                if not match:

                    raise ValueError(
                        "Could not determine "
                        "latest GitHub Actions run ID."
                    )

                run_id = int(
                    match.group(1)
                )

                print(
                    f"\nAutomatically selected "
                    f"Run ID: {run_id}"
                )

            # ------------------------------------------------
            # Build status
            # ------------------------------------------------

            status_result = (
                await client_session.call_tool(
                    "get_build_status",
                    {
                        "run_id": run_id
                    }
                )
            )

            status_text = (
                status_result.content[0].text
            )

            # Historical source must be tied to the selected CI commit.
            commit_sha = extract_commit_sha(status_text)

            print(
                "========== BUILD STATUS =========="
            )

            print(
                status_text
            )

            # ------------------------------------------------
            # Build logs
            # ------------------------------------------------

            logs_result = (
                await client_session.call_tool(
                    "get_build_logs",
                    {
                        "run_id": run_id
                    }
                )
            )

            logs = (
                logs_result.content[0].text
            )

            # ------------------------------------------------
            # Parse failures
            # ------------------------------------------------

            from agents.failure_parser import (
                extract_failure
            )

            failure = extract_failure(
                logs
            )

            print(
                "\n========== FAILURE ANALYSIS =========="
            )

            print(
                f"Failed Tests: "
                f"{failure['failed_tests']}"
            )

            print(
                f"Errors: "
                f"{failure['errors']}"
            )

            print(
                f"Assertions: "
                f"{failure['assertions']}"
            )

            failure_contexts = []

            implementation_files = []

            implementation_source = {}

            # ------------------------------------------------
            # Locate implementation targets
            # ------------------------------------------------

            for failure_item in failure[
                "failures"
            ]:

                test_name = failure_item[
                    "test"
                ]

                test_file = find_test_file(test_name)
                test_path = test_file.as_posix()

                # Reject paths that could escape the repository.
                if (
                    test_file.is_absolute()
                    or ".." in test_file.parts
                    or not test_path.endswith(".py")
                ):
                    raise RuntimeError(
                        "Invalid historical test path; diagnosis stopped."
                    )

                # Retrieve the test source from the exact failed CI commit.
                test_source = await fetch_historical_source(
                    client_session,
                    test_path,
                    commit_sha,
                )

                targets = await locate_historical_implementation_targets(
                    client_session,
                    test_name,
                    test_source,
                    commit_sha,
                )

                files = []

                for target in targets:
                    file_path = target["file"]

                    if file_path not in files:
                        files.append(file_path)

                    if file_path not in implementation_files:
                        implementation_files.append(file_path)

                    if file_path not in implementation_source:
                        implementation_source[file_path] = (
                            await fetch_historical_source(
                                client_session,
                                file_path,
                                commit_sha,
                            )
                        )

                failure_contexts.append(
                    {
                        "test": test_name,
                        "actual": failure_item[
                            "actual"
                        ],
                        "expected": failure_item[
                            "expected"
                        ],
                        "test_source": test_source,
                        "implementation_files": files,
                        "implementation_targets": targets
                    }
                )

            # ------------------------------------------------
            # LLM context
            # ------------------------------------------------

            context = f"""
You are a software failure diagnosis agent.

Analyze the failed CI/CD tests.

Use the provided evidence to determine the root cause.

IMPORTANT:

The implementation target has already been determined
by deterministic AST/source analysis.

You MUST use those authoritative targets.

Do NOT change the test.

Do NOT invent a different implementation file.

Do NOT invent a different implementation function.

Set review_status to READY_FOR_VALIDATION only when the supplied
source and failure evidence support a specific implementation defect.

Before assigning READY_FOR_VALIDATION:
- Inspect the actual implementation of the specified function.
- Verify that the implementation explains the observed actual result.
- Verify that the recommended fix addresses the demonstrated defect.
- If the implementation appears correct and the test expectation may be
  wrong, set review_status to REVIEW_REQUIRED.
- Never claim that a function returns its first argument if the supplied
  source shows it returns a + b.
- If source evidence contradicts the proposed root cause, set
  review_status to REVIEW_REQUIRED.

Return JSON only.

==================================================
BUILD STATUS
==================================================

{status_text}

==================================================
ERRORS
==================================================

{failure['errors']}

==================================================
STRUCTURED FAILURES
==================================================

{failure_contexts}

==================================================
IMPORTANT AUTHORITATIVE REPAIR TARGETS
==================================================

{[
    {
        "test": item["test"],
        "implementation_targets":
            item["implementation_targets"]
    }
    for item in failure_contexts
]}

==================================================
ALL IMPLEMENTATION FILES
==================================================

{[
    str(file)
    for file in implementation_files
]}

==================================================
IMPLEMENTATION SOURCE
==================================================

{implementation_source}

==================================================
REQUIRED OUTPUT
==================================================

Return exactly:

{{
    "diagnoses": [
        {{
            "test": "failed test",
            "actual": "actual result",
            "expected": "expected result",
            "root_cause": "specific root cause",
            "file": "implementation file",
            "function": "implementation function",
            "recommended_fix": "specific code change",
            "review_status": "READY_FOR_VALIDATION or REVIEW_REQUIRED"
        }}
    ]
}}

For every failed test, return exactly one diagnosis.

The "test" field may be either:

- the complete pytest node ID
- or only the test function name

The system will normalize it.

The "file" and "function" fields MUST match
the authoritative implementation target.
"""

            print(
                "\n========== LLM CONTEXT =========="
            )

            print(
                context
            )

            # ------------------------------------------------
            # Ask LLM
            # ------------------------------------------------

            diagnosis = ask_llm(
                context
            )

            # ------------------------------------------------
            # Target validation
            # ------------------------------------------------

            print(
                "\n========== TARGET VALIDATION =========="
            )

            diagnosis = validate_diagnosis_targets(
                diagnosis,
                failure_contexts
            )

            diagnosis = apply_source_evidence_gate(
                diagnosis,
                failure_contexts,
                implementation_source,
            )

            print(
                "Target validation and conservative source-evidence checks completed."
            )

            # ------------------------------------------------
            # Display diagnoses
            # ------------------------------------------------

            print(
                "\n========== AI DIAGNOSIS =========="
            )

            for index, item in enumerate(
                diagnosis["diagnoses"],
                start=1
            ):

                print(
                    f"\n----- Diagnosis {index} -----"
                )

                print(
                    f"Test: {item['test']}"
                )

                print(
                    f"Actual: {item['actual']}"
                )

                print(
                    f"Expected: {item['expected']}"
                )

                print(
                    f"Root Cause: "
                    f"{item['root_cause']}"
                )

                print(
                    f"File: {item['file']}"
                )

                print(
                    f"Function: "
                    f"{item['function']}"
                )

                print(
                    f"Recommended Fix: "
                    f"{item['recommended_fix']}"
                )

            return {
                "run_id": run_id,
                "build_status": status_text,
                "failure": failure,
                "failure_contexts": failure_contexts,
                "implementation_source": implementation_source,
                "diagnosis": diagnosis
            }


# ============================================================
# STANDALONE TEST
# ============================================================

async def main():

    result = await diagnose_run()

    print(
        "\n========== DIAGNOSIS COMPLETE =========="
    )

    print(
        json.dumps(
            result["diagnosis"],
            indent=2
        )
    )


if __name__ == "__main__":

    import anyio

    anyio.run(
        main
    )