from agents.import_resolver import resolve_imported_function_from_source


def test_returns_candidate_paths_from_historical_test_source(tmp_path):
    historical_test = (
        "\ufefffrom app.calculator import multiply\n"
        "def test_multiply():\n"
        "    assert multiply(4, 3) == 12\n"
    )

    assert resolve_imported_function_from_source(
        historical_test,
        "multiply",
        root=tmp_path,
    ) == [
        "app/calculator.py",
        "app/calculator/__init__.py",
    ]


def test_does_not_guess_function_without_import(tmp_path):
    assert resolve_imported_function_from_source(
        "def test_multiply():\n    assert multiply(4, 3) == 12\n",
        "multiply",
        root=tmp_path,
    ) == []


def test_rejects_relative_import(tmp_path):
    assert resolve_imported_function_from_source(
        "from .calculator import multiply\n",
        "multiply",
        root=tmp_path,
    ) == []


def test_rejects_multiple_import_modules(tmp_path):
    source = (
        "from app.calculator import multiply\n"
        "from app.other_calculator import multiply\n"
    )

    assert resolve_imported_function_from_source(
        source,
        "multiply",
        root=tmp_path,
    ) == []
