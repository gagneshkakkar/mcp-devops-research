from copy import deepcopy

import pytest

from agents.diagnosis_agent import apply_source_evidence_gate


TEST_NAME = "tests/test_project.py::test_add"
TARGET_FILE = "app/calculator.py"


def make_inputs(
    *,
    source="def add(a, b):\n    return a + b\n",
    test_source="def test_add():\n    assert add(2, 3) == 6\n",
    actual=5,
    expected=6,
    targets=None,
):
    diagnosis = {
        "diagnoses": [
            {
                "test": TEST_NAME,
                "file": TARGET_FILE,
                "function": "add",
                "actual": actual,
                "expected": expected,
                "review_status": "READY_FOR_VALIDATION",
                "recommended_fix": "Change the implementation",
            }
        ]
    }

    context = {
        "test": TEST_NAME,
        "test_source": test_source,
        "implementation_targets": (
            targets
            if targets is not None
            else [{"file": TARGET_FILE, "function": "add"}]
        ),
    }

    return diagnosis, [context], {TARGET_FILE: source}


def test_correct_add_implementation_with_wrong_expected_value_requires_review():
    diagnosis, contexts, sources = make_inputs()

    result = apply_source_evidence_gate(diagnosis, contexts, sources)

    item = result["diagnoses"][0]
    assert item["review_status"] == "REVIEW_REQUIRED"
    assert "observed actual value" in item["review_reason"]


@pytest.mark.parametrize(
    ("source", "contexts", "sources"),
    [
        (
            "def add(a, b):\n    return a + b\n",
            [],
            {TARGET_FILE: "def add(a, b):\n    return a + b\n"},
        ),
        (
            "def add(a, b):\n    return a + b\n",
            [{"test": TEST_NAME, "test_source": "assert add(2, 3) == 6",
              "implementation_targets": [{"file": TARGET_FILE, "function": "add"}]}],
            {},
        ),
        (
            "def add(a, b):\n    return a + b\n",
            [{"test": TEST_NAME, "test_source": "assert add(2, 3) == 6",
              "implementation_targets": [
                  {"file": TARGET_FILE, "function": "add"},
                  {"file": TARGET_FILE, "function": "add"},
              ]}],
            {TARGET_FILE: "def add(a, b):\n    return a + b\n"},
        ),
    ],
)
def test_missing_or_ambiguous_evidence_requires_review(source, contexts, sources):
    diagnosis, _, _ = make_inputs(source=source)

    result = apply_source_evidence_gate(diagnosis, contexts, sources)

    assert result["diagnoses"][0]["review_status"] == "REVIEW_REQUIRED"


def test_simple_defective_implementation_is_not_automatically_approved():
    diagnosis, contexts, sources = make_inputs(
        source="def add(a, b):\n    return a - b\n",
        actual=-1,
        expected=5,
        test_source="def test_add():\n    assert add(2, 3) == 5\n",
    )

    result = apply_source_evidence_gate(diagnosis, contexts, sources)

    # The gate cannot infer intended behavior from a mismatch alone.
    assert result["diagnoses"][0]["review_status"] == "REVIEW_REQUIRED"


def test_unsupported_function_logic_requires_review():
    diagnosis, contexts, sources = make_inputs(
        source=(
            "def add(a, b):\n"
            "    if a > 0:\n"
            "        return a + b\n"
            "    return b\n"
        )
    )

    result = apply_source_evidence_gate(diagnosis, contexts, sources)

    assert result["diagnoses"][0]["review_status"] == "REVIEW_REQUIRED"


def test_existing_review_required_status_is_preserved():
    diagnosis, contexts, sources = make_inputs()
    diagnosis["diagnoses"][0]["review_status"] = "REVIEW_REQUIRED"
    original = deepcopy(diagnosis)

    result = apply_source_evidence_gate(diagnosis, contexts, sources)

    assert result == original
