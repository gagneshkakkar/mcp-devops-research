import json
import re

from openai import OpenAI

from agents.function_extractor import extract_function


# --------------------------------------------------
# Ollama / OpenAI-compatible client
# --------------------------------------------------

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"
)


# --------------------------------------------------
# JSON parsing helpers
# --------------------------------------------------

def clean_json_response(content: str) -> str:
    """
    Clean common formatting problems from LLM JSON output.
    """

    content = content.strip()

    # Remove markdown code fences
    content = re.sub(
        r"^```(?:json)?\s*",
        "",
        content,
        flags=re.IGNORECASE
    )

    content = re.sub(
        r"\s*```$",
        "",
        content
    )

    content = content.strip()

    # Extract JSON object if additional text exists
    start = content.find("{")
    end = content.rfind("}")

    if start != -1 and end != -1:
        content = content[start:end + 1]

    return content


def parse_repair_response(
    content: str
) -> dict:
    """
    Parse the repair agent's JSON response.

    Handles common malformed JSON produced by
    local LLMs.
    """

    cleaned = clean_json_response(content)

    # --------------------------------------------------
    # Attempt 1: normal JSON
    # --------------------------------------------------

    try:
        return json.loads(cleaned)

    except json.JSONDecodeError as first_error:

        # --------------------------------------------------
        # Attempt 2: repair common control characters
        # --------------------------------------------------

        repaired = cleaned

        # Remove literal carriage returns
        repaired = repaired.replace(
            "\r",
            ""
        )

        # Convert literal newlines inside JSON strings
        # into escaped newlines.
        repaired = re.sub(
            r'(?<!\\)\n',
            r'\\n',
            repaired
        )

        try:
            return json.loads(repaired)

        except json.JSONDecodeError:

            # --------------------------------------------------
            # Attempt 3: extract simple JSON fields
            # --------------------------------------------------

            file_match = re.search(
                r'"file"\s*:\s*"([^"]*)"',
                cleaned
            )

            function_match = re.search(
                r'"function"\s*:\s*"([^"]*)"',
                cleaned
            )

            reason_match = re.search(
                r'"reason"\s*:\s*"([^"]*)"',
                cleaned
            )

            old_match = re.search(
                r'"old_code"\s*:\s*"((?:\\.|[^"\\])*)"',
                cleaned,
                re.DOTALL
            )

            new_match = re.search(
                r'"new_code"\s*:\s*"((?:\\.|[^"\\])*)"',
                cleaned,
                re.DOTALL
            )

            if (
                file_match
                and function_match
                and reason_match
                and old_match
                and new_match
            ):

                try:
                    return {
                        "file": file_match.group(1),
                        "function": function_match.group(1),
                        "reason": reason_match.group(1),
                        "old_code": json.loads(
                            '"' + old_match.group(1) + '"'
                        ),
                        "new_code": json.loads(
                            '"' + new_match.group(1) + '"'
                        )
                    }

                except Exception:
                    pass

            raise ValueError(
                "Repair LLM returned invalid JSON "
                "after repair attempts: "
                f"{first_error}"
            )


# --------------------------------------------------
# Normalize paths
# --------------------------------------------------

def normalize_path(
    file_path: str
) -> str:
    """
    Normalize Windows/Linux path separators.
    """

    return (
        file_path
        .replace("\\", "/")
        .strip()
    )


# --------------------------------------------------
# Validate repair structure
# --------------------------------------------------

def validate_repair_structure(
    repair: dict,
    file_path: str,
    function_name: str,
    source_code: str
) -> dict:
    """
    Validate the structural correctness of an
    LLM-generated repair before applying it.
    """

    required_fields = [
        "file",
        "function",
        "reason",
        "old_code",
        "new_code"
    ]

    # --------------------------------------------------
    # Required fields
    # --------------------------------------------------

    for field in required_fields:

        if field not in repair:

            raise ValueError(
                f"Repair response missing '{field}'."
            )

    # --------------------------------------------------
    # Normalize target paths
    # --------------------------------------------------

    expected_file = normalize_path(
        file_path
    )

    returned_file = normalize_path(
        repair["file"]
    )

    if returned_file != expected_file:

        raise ValueError(
            "Repair rejected: LLM returned "
            f"unexpected file '{returned_file}'. "
            f"Expected '{expected_file}'."
        )

    # --------------------------------------------------
    # Validate function
    # --------------------------------------------------

    returned_function = (
        str(
            repair["function"]
        ).strip()
    )

    if returned_function != function_name:

        raise ValueError(
            "Repair rejected: LLM returned "
            f"unexpected function '{returned_function}'. "
            f"Expected '{function_name}'."
        )

    # --------------------------------------------------
    # Validate code
    # --------------------------------------------------

    old_code = repair["old_code"]
    new_code = repair["new_code"]

    if not isinstance(
        old_code,
        str
    ):

        raise ValueError(
            "Repair rejected: old_code must be a string."
        )

    if not isinstance(
        new_code,
        str
    ):

        raise ValueError(
            "Repair rejected: new_code must be a string."
        )

    old_code = old_code.strip()
    new_code = new_code.strip()

    if not old_code:

        raise ValueError(
            "Repair rejected: old_code is empty."
        )

    if not new_code:

        raise ValueError(
            "Repair rejected: new_code is empty."
        )

    if old_code == new_code:

        raise ValueError(
            "Repair rejected: old_code and "
            "new_code are identical."
        )

    # --------------------------------------------------
    # Verify exact occurrence
    # --------------------------------------------------

    occurrence_count = source_code.count(
        old_code
    )

    if occurrence_count == 0:

        raise ValueError(
            "Repair rejected: old_code was not "
            "found in the affected function."
        )

    if occurrence_count > 1:

        raise ValueError(
            "Repair rejected: old_code occurs "
            f"{occurrence_count} times in the "
            "affected function."
        )

    # --------------------------------------------------
    # Store normalized values
    # --------------------------------------------------

    repair["file"] = expected_file
    repair["function"] = returned_function
    repair["old_code"] = old_code
    repair["new_code"] = new_code

    return repair


# --------------------------------------------------
# Generate repair
# --------------------------------------------------

def generate_repair(
    diagnosis: str,
    file_path: str,
    function_name: str
) -> dict:
    """
    Generate a minimal code repair using the local LLM.

    The LLM is instructed to return only the smallest
    code fragment that needs to change.
    """

    # --------------------------------------------------
    # Extract authoritative function source
    # --------------------------------------------------

    source_code = extract_function(
        file_path,
        function_name
    )

    # --------------------------------------------------
    # Build repair prompt
    # --------------------------------------------------

    prompt = f"""
You are an autonomous code repair agent.

Your job is to generate a minimal and safe repair
for the diagnosed CI failure.

IMPORTANT RULES:

1. Modify ONLY the affected function.
2. Do NOT modify the tests.
3. Do NOT modify unrelated code.
4. Do NOT invent files.
5. Return valid JSON only.
6. old_code MUST be a small exact code fragment
   copied from the affected function.
7. new_code MUST be the corrected replacement
   for old_code.
8. Prefer changing the smallest possible
   expression or statement.
9. Do NOT return the entire function unless
   absolutely necessary.
10. old_code and new_code should normally be
    a single line.
11. Do not include markdown.
12. Use forward slashes in the JSON file path.
13. Do not include extra text before or after JSON.
14. old_code must exist exactly in the supplied
    affected function source.
15. new_code must fix the diagnosed problem.
16. Do not change function names or signatures.
17. Do not modify unrelated statements.

TARGET FILE:
{file_path}

TARGET FUNCTION:
{function_name}

DIAGNOSIS:
{diagnosis}

AFFECTED FUNCTION SOURCE:
{source_code}

Return exactly:

{{
    "file": "{file_path.replace(chr(92), '/')}",
    "function": "{function_name}",
    "reason": "short explanation",
    "old_code": "small exact code fragment to replace",
    "new_code": "corrected replacement code"
}}
"""

    # --------------------------------------------------
    # LLM request
    # --------------------------------------------------

    response = client.chat.completions.create(
        model="qwen2.5-coder:7b",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    content = (
        response
        .choices[0]
        .message
        .content
        .strip()
    )

    print(
        "\n========== RAW REPAIR LLM RESPONSE =========="
    )

    print(
        content
    )

    # --------------------------------------------------
    # Parse response
    # --------------------------------------------------

    repair = parse_repair_response(
        content
    )

    # --------------------------------------------------
    # Validate repair
    # --------------------------------------------------

    repair = validate_repair_structure(
        repair=repair,
        file_path=file_path,
        function_name=function_name,
        source_code=source_code
    )

    return repair


# --------------------------------------------------
# Standalone test
# --------------------------------------------------

if __name__ == "__main__":

    print(
        "========== REPAIR AGENT TEST =========="
    )

    test_diagnosis = """
Failed Test:
tests/test_project.py::test_multiply

Actual Result:
7

Expected Result:
12

Root Cause:
The multiply function is adding the two
numbers instead of multiplying them.

Recommended Fix:
Return the product of the two numbers.

Implementation File:
app/calculator.py

Implementation Function:
multiply
"""

    try:

        result = generate_repair(
            diagnosis=test_diagnosis,
            file_path="app/calculator.py",
            function_name="multiply"
        )

        print(
            "\n========== VALIDATED REPAIR =========="
        )

        print(
            result
        )

    except Exception as error:

        print(
            "\n========== REPAIR FAILED =========="
        )

        print(
            error
        )