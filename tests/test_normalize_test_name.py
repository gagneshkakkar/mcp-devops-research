from agents.diagnosis_agent import normalize_test_name


KNOWN_TESTS = [
    "tests/test_project.py::test_multiply",
    "tests/test_project.py::test_divide",
]


def test_normalizes_function_name_alias():
    assert normalize_test_name("multiply", KNOWN_TESTS) == (
        "tests/test_project.py::test_multiply"
    )


def test_normalizes_another_function_name_alias():
    assert normalize_test_name("divide", KNOWN_TESTS) == (
        "tests/test_project.py::test_divide"
    )


def test_normalizes_test_function_name():
    assert normalize_test_name("test_multiply", KNOWN_TESTS) == (
        "tests/test_project.py::test_multiply"
    )


def test_preserves_exact_node_id():
    expected = "tests/test_project.py::test_multiply"
    assert normalize_test_name(expected, KNOWN_TESTS) == expected


def test_rejects_unknown_test_name():
    assert normalize_test_name("subtract", KNOWN_TESTS) is None


def test_rejects_ambiguous_function_name_alias():
    ambiguous_tests = [
        "tests/test_project.py::test_multiply",
        "tests/test_other.py::test_multiply",
    ]
    assert normalize_test_name("multiply", ambiguous_tests) is None
