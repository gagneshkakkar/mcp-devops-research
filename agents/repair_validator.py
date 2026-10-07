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
    the reported CI/CD failure.

    The validator uses deterministic evidence first:

    - failed test
    - actual result
    - expected result
    - implementation source
    - target file
    - target function
    - exact old code
    - exact new code

    The diagnosis is treated as supporting information only.
    """

    # --------------------------------------------------
    # Basic deterministic checks
    # --------------------------------------------------

    if not file_path:
        return {
            "approved": False,
            "reason": "Repair rejected: target file is missing."
        }

    if not function_name:
        return {
            "approved": False,
            "reason": "Repair rejected: target function is missing."
        }

    if not old_code:
        return {
            "approved": False,
            "reason": "Repair rejected: old_code is empty."
        }

    if not new_code:
        return {
            "approved": False,
            "reason": "Repair rejected: new_code is empty."
        }

    if old_code == new_code:
        return {
            "approved": False,
            "reason": "Repair rejected: old_code and new_code are identical."
        }

    # --------------------------------------------------
    # Verify original code exists in implementation
    # --------------------------------------------------

    if implementation_source:

        if old_code not in implementation_source:

            return {
                "approved": False,
                "reason": (
                    "Repair rejected: old_code does not exist "
                    "in the supplied implementation source."
                )
            }

    # --------------------------------------------------
    # Strong validation prompt
    # --------------------------------------------------

    prompt = f"""
You are a strict software repair validation agent.

Your job is to determine whether the EXACT proposed code change
correctly fixes the reported CI/CD failure.

IMPORTANT:

The proposed patch itself is authoritative.

Do NOT reject a correct patch merely because the diagnosis text
is incomplete, vague, or incorrectly worded.

The diagnosis is ONLY supporting context.

The most important evidence is:

1. Failed test
2. Actual result
3. Expected result
4. Original implementation
5. Target function
6. OLD CODE
7. NEW CODE

==================================================
FAILED TEST
==================================================

{failed_test}

==================================================
ACTUAL RESULT
==================================================

{actual}

==================================================
EXPECTED RESULT
==================================================

{expected}

==================================================
TARGET FILE
==================================================

{file_path}

==================================================
TARGET FUNCTION
==================================================

{function_name}

==================================================
ORIGINAL IMPLEMENTATION
==================================================

{implementation_source}

==================================================
DIAGNOSIS
==================================================

{diagnosis}

IMPORTANT:

The diagnosis may be wrong or poorly worded.

Do NOT blindly trust the diagnosis.

Independently compare the implementation and proposed patch
with the actual and expected results.

==================================================
EXACT PROPOSED PATCH
==================================================

OLD CODE:
{old_code}

NEW CODE:
{new_code}

==================================================
VALIDATION PROCEDURE
==================================================

Perform the following checks IN ORDER.

CHECK 1:
Does OLD CODE actually exist in the original implementation?

If no:
REJECT.

CHECK 2:
Does the target function correspond to the failed behavior?

If no:
REJECT.

CHECK 3:
Does NEW CODE differ from OLD CODE?

If no:
REJECT.

CHECK 4:
Would replacing OLD CODE with NEW CODE move the implementation
toward the EXPECTED RESULT?

Use the actual failure evidence to determine this.

CHECK 5:
Does the patch modify the implementation rather than the test?

If it modifies test assertions, expected values, test inputs,
or test files, REJECT.

CHECK 6:
Is the proposed change minimal?

A small correction to the faulty expression is preferred.

CHECK 7:
Does the proposed change introduce an obvious new defect?

If yes:
REJECT.

==================================================
CRITICAL EXAMPLE
==================================================

Suppose:

FAILED TEST:
test_divide

Actual Result:
20

Expected Result:
5

Original implementation:

def divide(a, b):
    return a * b

Proposed patch:

OLD CODE:
return a * b

NEW CODE:
return a / b

This is a VALID repair.

APPROVE it.

Do NOT reject it because the diagnosis text says something
unclear or incorrect.

==================================================
SECOND EXAMPLE
==================================================

Suppose:

FAILED TEST:
test_multiply

Actual Result:
7

Expected Result:
12

Original implementation:

def multiply(a, b):
    return a + b

Proposed patch:

OLD CODE:
return a + b

NEW CODE:
return a * b

This is a VALID repair.

APPROVE it.

==================================================
INVALID EXAMPLE
==================================================

Suppose:

FAILED TEST:
test_multiply

Actual Result:
7

Expected Result:
12

Original implementation:

def multiply(a, b):
    return a + b

Proposed patch:

OLD CODE:
return a + b

NEW CODE:
return 7

This should normally be REJECTED because it hardcodes a result
instead of correctly implementing multiplication.

==================================================
INVALID TEST MODIFICATION
==================================================

If the proposed patch changes:

assert multiply(4, 3) == 12

to:

assert multiply(4, 3) == 7

REJECT the repair.

==================================================
IMPORTANT DECISION RULE
==================================================

When diagnosis text conflicts with the actual implementation
and proposed patch:

TRUST THE ACTUAL IMPLEMENTATION + FAILURE EVIDENCE + PROPOSED PATCH.

Do NOT blindly trust the diagnosis.

==================================================
OUTPUT
==================================================

Return valid JSON only.

Do not return markdown.

Do not include explanations outside JSON.

Return exactly one of:

{{
    "approved": true,
    "reason": "short evidence-based explanation"
}}

OR:

{{
    "approved": false,
    "reason": "short evidence-based explanation"
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
        ],
        temperature=0
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

        result = json.loads(content)

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

            result = json.loads(
                repaired_content
            )

        except json.JSONDecodeError as error:

            print(
                "\n========== RAW VALIDATOR RESPONSE =========="
            )

            print(content)

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