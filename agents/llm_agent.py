from openai import OpenAI


client = OpenAI(
    base_url="http://localhost:20128/v1"
)


def diagnose_failure(context: str) -> str:
    """Ask the LLM to diagnose a CI/CD failure."""

    prompt = f"""
You are a DevOps failure diagnosis agent.

Analyze the following CI/CD failure information.

Identify:
1. The failed test.
2. The actual result.
3. The expected result.
4. The root cause.
5. The source file responsible.
6. The recommended code fix.

CI/CD FAILURE INFORMATION:

{context}

Give a concise but clear diagnosis.
"""

    response = client.chat.completions.create(
        model="big-pickle",
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )

    return response.choices[0].message.content


if __name__ == "__main__":

   test_context = """
Failed Test:
tests/test_project.py::test_multiply

Assertion:
assert multiply(4, 3) == 12

Actual result:
7

Expected result:
12

Implementation file:
app/calculator.py

Implementation:

def multiply(a: float, b: float) -> float:
    \"\"\"Return the product of two numbers.\"\"\"
    return a + b
"""

diagnosis = diagnose_failure(test_context)

print("========== AI DIAGNOSIS ==========")
print(diagnosis)