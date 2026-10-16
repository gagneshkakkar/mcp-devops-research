
import json
from pathlib import Path

from openai import OpenAI


ROOT = Path(__file__).resolve().parent.parent
CASE_DIR = ROOT / "benchmark" / "failures" / "F10"
RESULT_PATH = ROOT / "benchmark" / "results" / "f10_prompt_test.json"

MODEL_NAME = "qwen2.5-coder:7b"

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
    timeout=180.0,
    max_retries=0,
)


def main():
    metadata = json.loads(
        (CASE_DIR / "metadata.json").read_text(encoding="utf-8")
    )

    broken_source = (
        CASE_DIR / "broken" / "calculator.py"
    ).read_text(encoding="utf-8")

    prompt = f"""
Repair the Python function in the supplied file.

Failure: {metadata["title"]}
Root cause: {metadata["root_cause"]}

Required behavioral contract:
- The function is called with no arguments.
- If the environment variable BENCHMARK_API_URL is set,
  return its value.
- If the variable is missing, return exactly:
  https://example.test/api
- Do not raise an exception merely because the variable is missing.
- Preserve the function name and signature.
- Do not hardcode behavior for only one environment state.
- Return the complete corrected Python file, with no Markdown fences.
- Do not include explanations.

Broken source:
--------------------
{broken_source}
--------------------

Return the corrected Python source only.
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )

    generated = response.choices[0].message.content

    if not generated or not generated.strip():
        raise ValueError("The model returned an empty response.")

    generated = generated.strip()

    if generated.startswith("```"):
        lines = generated.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        generated = "\n".join(lines).strip()

    generated += "\n"

    # Syntax-check the response before evaluating it.
    compile(generated, "<f10_prompt_test>", "exec")

    namespace = {"__name__": "f10_prompt_test"}
    exec(generated, namespace)

    function = namespace.get(metadata["function"])
    if not callable(function):
        raise ValueError("Generated source lacks the expected function.")

    # Evaluate both environment states without changing the parent process.
    import os

    variable_name = "BENCHMARK_API_URL"
    was_set = variable_name in os.environ
    previous_value = os.environ.get(variable_name)

    outcomes = {}

    try:
        os.environ.pop(variable_name, None)
        outcomes["unset_variable"] = function()

        os.environ[variable_name] = "https://configured.example/api"
        outcomes["set_variable"] = function()
    finally:
        if was_set:
            os.environ[variable_name] = previous_value
        else:
            os.environ.pop(variable_name, None)

    passed = (
        outcomes["unset_variable"] == metadata["expected_output"]
        and outcomes["set_variable"] == "https://configured.example/api"
    )

    result = {
        "experiment": "f10_explicit_behavior_contract_prompt",
        "model": MODEL_NAME,
        "case_id": "F10",
        "status": "passed" if passed else "test_failed",
        "expected_when_unset": metadata["expected_output"],
        "actual_when_unset": outcomes["unset_variable"],
        "expected_when_set": "https://configured.example/api",
        "actual_when_set": outcomes["set_variable"],
        "generated_source": generated,
        "notes": [
            "Separate prompt experiment; existing RAG and LOCO results are untouched.",
            "The environment variable is restored after evaluation.",
            "The generated code is executed locally; use only trusted benchmark cases.",
        ],
    }

    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("F10 prompt experiment:", result["status"])
    print("Variable unset:", outcomes["unset_variable"])
    print("Variable set:", outcomes["set_variable"])
    print("Results saved to:", RESULT_PATH)


if __name__ == "__main__":
    main()
