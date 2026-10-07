import re


def extract_failure(log_text: str) -> dict:
    """
    Extract structured failure information from
    pytest/GitHub Actions logs.

    Supports multiple failed tests in the same CI run.
    """

    result = {
        "failed_tests": [],
        "errors": [],
        "assertions": [],
        "failures": [],
    }

    # --------------------------------------------------
    # 1. Find failed pytest tests
    # --------------------------------------------------

    failed_tests = re.findall(
        r"FAILED\s+([^\s]+)",
        log_text
    )

    result["failed_tests"] = list(
        dict.fromkeys(failed_tests)
    )

    # --------------------------------------------------
    # 2. Detect error types
    # --------------------------------------------------

    if "AssertionError" in log_text:

        result["errors"].append(
            "AssertionError"
        )

    # --------------------------------------------------
    # 3. Extract numeric assertions
    #
    # Example:
    #
    # E       assert 7 == 12
    #
    # We deliberately require "assert" followed by
    # numeric values.
    # --------------------------------------------------

    assertions = re.findall(
        r"\bassert\s+(-?\d+(?:\.\d+)?)\s*==\s*(-?\d+(?:\.\d+)?)",
        log_text
    )

    for actual, expected in assertions:

        assertion = {
            "actual": actual,
            "expected": expected,
        }

        if assertion not in result["assertions"]:

            result["assertions"].append(
                assertion
            )

    # --------------------------------------------------
    # 4. Pair failed tests with assertions
    #
    # This creates a structured failure record.
    # --------------------------------------------------

    for index, test in enumerate(
        result["failed_tests"]
    ):

        failure = {
            "test": test,
            "actual": None,
            "expected": None,
        }

        # If an assertion exists at the same
        # index, associate it with this test.
        if index < len(
            result["assertions"]
        ):

            failure["actual"] = (
                result["assertions"][index]["actual"]
            )

            failure["expected"] = (
                result["assertions"][index]["expected"]
            )

        result["failures"].append(
            failure
        )

    return result


if __name__ == "__main__":

    sample_log = """
    FAILED tests/test_project.py::test_multiply - assert 7 == 12
    FAILED tests/test_project.py::test_divide - assert 20 == 5

    E       assert 7 == 12
    E       assert 20 == 5

    AssertionError
    """

    result = extract_failure(
        sample_log
    )

    print(
        "========== PARSER RESULT =========="
    )

    print(
        result
    )

    print(
        "\n========== STRUCTURED FAILURES =========="
    )

    for failure in result["failures"]:

        print(
            f"Test: {failure['test']}"
        )

        print(
            f"Actual: {failure['actual']}"
        )

        print(
            f"Expected: {failure['expected']}"
        )

        print()