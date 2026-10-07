import json
import re
from pathlib import Path

from openai import OpenAI

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


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
    ]
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
    Determine which implementation functions are called by
    the failed test.

    This is deterministic AST analysis and is therefore
    authoritative.
    """

    import ast

    test_file = find_test_file(
        failed_test
    )

    test_function = find_test_function(
        failed_test
    )

    if not test_file.exists():

        return []

    source = test_file.read_text(
        encoding="utf-8"
    )

    tree = ast.parse(
        source
    )

    target_node = None

    for node in tree.body:

        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef
            )
        ):

            if node.name == test_function:

                target_node = node

                break

    if target_node is None:

        return []

    called_functions = []

    for node in ast.walk(
        target_node
    ):

        if isinstance(
            node,
            ast.Call
        ):

            if isinstance(
                node.func,
                ast.Name
            ):

                called_functions.append(
                    node.func.id
                )

            elif isinstance(
                node.func,
                ast.Attribute
            ):

                called_functions.append(
                    node.func.attr
                )

    called_functions = list(
        dict.fromkeys(
            called_functions
        )
    )

    targets = []

    for function_name in called_functions:

        files = find_function_definition(
            function_name
        )

        for file_path in files:

            targets.append(
                {
                    "file": str(
                        file_path
                    ),
                    "function": function_name
                }
            )

    return targets


# ============================================================
# DIAGNOSIS
# ============================================================

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

                test_file = find_test_file(
                    test_name
                )

                test_source = read_file(
                    test_file
                )

                targets = (
                    locate_implementation_targets(
                        test_name
                    )
                )

                files = []

                for target in targets:

                    file_path = target[
                        "file"
                    ]

                    if file_path not in files:

                        files.append(
                            file_path
                        )

                    if file_path not in implementation_files:

                        implementation_files.append(
                            file_path
                        )

                    if file_path not in implementation_source:

                        implementation_source[
                            file_path
                        ] = read_file(
                            Path(
                                file_path
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
            "recommended_fix": "specific code change"
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

            print(
                "All LLM repair targets match "
                "static source analysis."
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