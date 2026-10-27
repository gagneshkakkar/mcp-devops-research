from pathlib import Path

import pytest

from agents.repair_agent import validate_repair_structure


SOURCE = """def multiply(a, b):
    return a + b
"""


def make_repair(old_code="return a + b", new_code="return a * b"):
    return {
        "file": "app/calculator.py",
        "function": "multiply",
        "reason": "Use multiplication instead of addition",
        "old_code": old_code,
        "new_code": new_code,
    }


def test_validator_accepts_exact_python_replacement():
    result = validate_repair_structure(
        repair=make_repair(),
        file_path="app/calculator.py",
        function_name="multiply",
        source_code=SOURCE,
    )

    assert result["old_code"] == "return a + b"
    assert result["new_code"] == "return a * b"


def test_validator_rejects_semicolon_not_present_in_source():
    with pytest.raises(ValueError, match="old_code was not found"):
        validate_repair_structure(
            repair=make_repair(old_code="return a + b;"),
            file_path="app/calculator.py",
            function_name="multiply",
            source_code=SOURCE,
        )


def test_validator_rejects_ambiguous_old_code():
    repeated_source = SOURCE + "\n# return a + b\n"

    with pytest.raises(ValueError, match="occurs 2 times"):
        validate_repair_structure(
            repair=make_repair(),
            file_path="app/calculator.py",
            function_name="multiply",
            source_code=repeated_source,
        )
