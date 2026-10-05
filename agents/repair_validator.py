import json

from openai import OpenAI


# --------------------------------------------------
# Ollama / Local LLM
# --------------------------------------------------

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"
)


# --------------------------------------------------
# Validate repair
# --------------------------------------------------

def validate_repair(
    diagnosis: str,
    file_path: str,
    function_name: str,
    old_code: str,
    new_code: str,
    implementation_source: str = "",
    failed_test: str = "",
    actual: str = "",
    expected: str = ""
) -> dict:
    """
    Validate whether a proposed repair correctly addresses
    the diagnosed CI/CD failure.

    The validator receives the original implementation source
    and failure evidence so that it can independently check
    whether the proposed change makes sense.
    """

    # --------------------------------------------------
    # Validation prompt
    # --------------------------------------------------

    prompt = f"""
You are a strict software repair validation agent.

Your job is to determine whether a proposed code repair
actually fixes the reported CI/CD failure.

You MUST use the evidence provided below.

==================================================
FAILED TEST
==================================================

{failed_test}

Actual Result:
{actual}

Expected Result:
{expected}


==================================================
DIAGNOSIS
==================================================

{diagnosis}


==================================================
TARGET FILE
==================================================

{file_path}


==================================================
TARGET FUNCTION
==================================================

{function_name}


==================================================
ORIGINAL IMPLEMENTATION SOURCE
==================================================

{implementation_source}


==================================================
PROPOSED CHANGE
==================================================

OLD CODE:
{old_code}

NEW CODE:
{new_code}


==================================================
VALIDATION RULES
==================================================

1. The proposed change must address the actual root cause
   shown by the implementation source.

2. The proposed change must explain the difference between
   the actual result and expected result.

3. The proposed change must be applied to the implementation,
   not the test.

4. The target function must be the function responsible for
   the failure.

5. Do not approve a repair merely because the new code looks
   reasonable.

6. Compare the old implementation with the expected behavior.

7. If the diagnosis incorrectly blames the test while the
   implementation clearly contradicts the expected behavior,
   REJECT the repair.

8. If the proposed repair changes test behavior, inputs,
   expected values, or test assertions, REJECT it.

9. The repair should be minimal.

10. The repair must not introduce an obvious new defect.

11. Return valid JSON only.

12. Do not return markdown.

13. Do not include explanations outside the JSON.

==================================================
IMPORTANT EXAMPLE
==================================================

If:

divide(10, 2)

returns:

20

but the expected result is:

5

and the implementation contains:

return a * b

then the implementation is incorrect.

The correct repair is:

return a / b

Do NOT modify the test.

==================================================

Return exactly:

{{
    "approved": true,
    "reason": "short explanation based on the evidence"
}}

OR:

{{
    "approved": false,
    "reason": "short explanation of why the repair is invalid"
}}
"""

    # --------------------------------------------------
    # Call validator LLM
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

    content = response.choices[0].message.content.strip()

    # --------------------------------------------------
    # Remove markdown code fences
    # --------------------------------------------------

    if content.startswith("```"):

        lines = content.splitlines()

        if lines and lines[0].startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        content = "\n".join(lines).strip()

    # --------------------------------------------------
    # Parse JSON
    # --------------------------------------------------

    try:

        result = json.loads(
            content
        )

    except json.JSONDecodeError:

        # --------------------------------------------------
        # Repair invalid Windows backslashes
        # --------------------------------------------------

        repaired_content = ""

        i = 0

        while i < len(content):

            character = content[i]

            if character == "\\":

                if i + 1 < len(content):

                    next_character = content[
                        i + 1
                    ]

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

            result = json.loads(
                repaired_content
            )

        except json.JSONDecodeError as error:

            print(
                "\n========== RAW VALIDATOR RESPONSE =========="
            )

            print(
                content
            )

            raise ValueError(
                "Validator returned invalid JSON "
                f"after repair attempt: {error}"
            )

    # --------------------------------------------------
    # Validate response structure
    # --------------------------------------------------

    if "approved" not in result:

        raise ValueError(
            "Validator response missing 'approved'."
        )

    if "reason" not in result:

        raise ValueError(
            "Validator response missing 'reason'."
        )

    if not isinstance(
        result["approved"],
        bool
    ):

        raise ValueError(
            "Validator 'approved' field must be boolean."
        )

    return result