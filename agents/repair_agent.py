import json

from openai import OpenAI

from agents.function_extractor import extract_function


# ============================================================
# Ollama / Local LLM
# ============================================================

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"
)


# ============================================================
# JSON PARSER
# ============================================================

def parse_repair_response(
    content: str
) -> dict:
    """
    Parse the repair-agent response.

    Handles:
    1. Normal JSON
    2. Markdown code fences
    3. Common invalid Windows-path escaping
    4. Literal newlines inside JSON strings produced by
       smaller local models
    """

    content = content.strip()

    # --------------------------------------------------------
    # Remove markdown fences
    # --------------------------------------------------------

    if content.startswith("```"):

        lines = content.splitlines()

        if lines and lines[0].startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        content = "\n".join(
            lines
        ).strip()

    # --------------------------------------------------------
    # Attempt 1: normal JSON
    # --------------------------------------------------------

    try:

        return json.loads(
            content
        )

    except json.JSONDecodeError:
        pass

    # --------------------------------------------------------
    # Attempt 2:
    #
    # Escape literal control characters occurring inside
    # JSON strings.
    #
    # This is needed because a local LLM may return:
    #
    # "old_code": "line1
    # line2"
    #
    # instead of:
    #
    # "old_code": "line1\nline2"
    # --------------------------------------------------------

    repaired = []

    inside_string = False
    escaped = False

    for character in content:

        # ----------------------------------------------
        # Handle escaped characters
        # ----------------------------------------------

        if escaped:

            repaired.append(
                character
            )

            escaped = False

            continue

        if character == "\\":

            repaired.append(
                character
            )

            escaped = True

            continue

        # ----------------------------------------------
        # Handle JSON string boundaries
        # ----------------------------------------------

        if character == '"':

            inside_string = (
                not inside_string
            )

            repaired.append(
                character
            )

            continue

        # ----------------------------------------------
        # Escape literal control characters inside
        # JSON strings
        # ----------------------------------------------

        if inside_string:

            if character == "\n":

                repaired.append(
                    "\\n"
                )

                continue

            if character == "\r":

                repaired.append(
                    "\\r"
                )

                continue

            if character == "\t":

                repaired.append(
                    "\\t"
                )

                continue

        repaired.append(
            character
        )

    repaired_content = "".join(
        repaired
    )

    # --------------------------------------------------------
    # Attempt 3: parse repaired JSON
    # --------------------------------------------------------

    try:

        return json.loads(
            repaired_content
        )

    except json.JSONDecodeError:

        # ----------------------------------------------------
        # Attempt 4:
        #
        # Repair invalid backslashes in Windows paths.
        # ----------------------------------------------------

        final_content = []

        i = 0

        while i < len(
            repaired_content
        ):

            character = (
                repaired_content[i]
            )

            if character == "\\":

                if (
                    i + 1
                    < len(
                        repaired_content
                    )
                ):

                    next_character = (
                        repaired_content[
                            i + 1
                        ]
                    )

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

                    if (
                        next_character
                        in valid_escapes
                    ):

                        final_content.append(
                            "\\"
                        )

                    else:

                        final_content.append(
                            "\\\\"
                        )

                else:

                    final_content.append(
                        "\\\\"
                    )

            else:

                final_content.append(
                    character
                )

            i += 1

        final_content = "".join(
            final_content
        )

        try:

            return json.loads(
                final_content
            )

        except json.JSONDecodeError as error:

            print(
                "\n========== RAW REPAIR LLM RESPONSE =========="
            )

            print(
                content
            )

            raise ValueError(
                "Repair LLM returned invalid JSON "
                f"after repair attempts: {error}"
            )


# ============================================================
# REPAIR GENERATION
# ============================================================

def generate_repair(
    diagnosis: str,
    file_path: str,
    function_name: str
) -> dict:
    """
    Generate a minimal repair for the affected function.
    """

    # --------------------------------------------------------
    # Extract only affected function
    # --------------------------------------------------------

    source_code = extract_function(
        file_path,
        function_name
    )

    # --------------------------------------------------------
    # Prompt
    # --------------------------------------------------------

    prompt = f"""
You are an automated software repair agent.

A CI/CD failure has been diagnosed.

Generate the smallest possible code change that fixes
the diagnosed problem.

RULES:

1. Modify only the affected function.
2. Do not modify tests.
3. Do not modify unrelated code.
4. Do not invent files.
5. Return valid JSON only.
6. old_code must be copied exactly from the provided function.
7. new_code must be the corrected version of that code.
8. old_code must be specific enough to identify the intended change.
9. Do not include markdown outside the JSON.
10. Use forward slashes in the JSON "file" value.
11. Do not use Windows backslashes in JSON strings.
12. Encode newlines inside old_code and new_code as \\n.
13. Do not return literal line breaks inside JSON string values.

TARGET FILE:
{file_path}

TARGET FUNCTION:
{function_name}

DIAGNOSIS:
{diagnosis}

AFFECTED FUNCTION SOURCE:
{source_code}

AFFECTED FUNCTION SOURCE:
{source_code}

Return exactly:

{{
    "file": "{file_path.replace(chr(92), '/')}",
    "function": "{function_name}",
    "reason": "short explanation",
    "old_code": "exact code to replace",
    "new_code": "replacement code"
}}
"""

    # --------------------------------------------------------
    # LLM request
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Parse response
    # --------------------------------------------------------

    repair = parse_repair_response(
        content
    )

    # --------------------------------------------------------
    # Required fields
    # --------------------------------------------------------

    required_fields = [
        "file",
        "function",
        "reason",
        "old_code",
        "new_code",
    ]

    for field in required_fields:

        if field not in repair:

            raise ValueError(
                f"Repair response missing "
                f"'{field}'."
            )

    # --------------------------------------------------------
    # Normalize file
    # --------------------------------------------------------

    repair["file"] = (
        repair["file"]
        .strip()
        .strip("`")
        .replace(
            "\\",
            "/"
        )
    )

    expected_file = (
        file_path
        .replace(
            "\\",
            "/"
        )
    )

    # --------------------------------------------------------
    # Target file validation
    # --------------------------------------------------------

    if repair["file"] != expected_file:

        raise ValueError(
            "Repair rejected: incorrect target file."
        )

    # --------------------------------------------------------
    # Target function validation
    # --------------------------------------------------------

    if repair["function"] != function_name:

        raise ValueError(
            "Repair rejected: incorrect "
            "target function."
        )

    # --------------------------------------------------------
    # Validate old_code
    # --------------------------------------------------------

    old_code = repair.get(
        "old_code",
        ""
    )

    if not old_code:

        raise ValueError(
            "Repair rejected: old_code is empty."
        )

    # --------------------------------------------------------
    # Validate new_code
    # --------------------------------------------------------

    new_code = repair.get(
        "new_code",
        ""
    )

    if not new_code:

        raise ValueError(
            "Repair rejected: new_code is empty."
        )

    # --------------------------------------------------------
    # old_code must exist in affected function
    # --------------------------------------------------------

    occurrence_count = (
        source_code.count(
            old_code
        )
    )

    if occurrence_count == 0:

        raise ValueError(
            "Repair rejected: old_code was not found "
            "in the affected function."
        )

    if occurrence_count > 1:

        raise ValueError(
            "Repair rejected: old_code is ambiguous."
        )

    # --------------------------------------------------------
    # old_code and new_code must differ
    # --------------------------------------------------------

    if old_code == new_code:

        raise ValueError(
            "Repair rejected: old_code and "
            "new_code are identical."
        )

    # --------------------------------------------------------
    # Return validated repair
    # --------------------------------------------------------

    repair["validation"] = {
        "valid": True,
        "occurrences": occurrence_count
    }

    return repair


# ============================================================
# STANDALONE TEST
# ============================================================

if __name__ == "__main__":

    print(
        "Repair agent module loaded successfully."
    )