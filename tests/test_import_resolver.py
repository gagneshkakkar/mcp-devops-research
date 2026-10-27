from agents.import_resolver import resolve_imported_function


def test_explicit_import_resolves_only_imported_module(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "benchmark").mkdir()
    (tmp_path / "tests").mkdir()

    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "app" / "calculator.py").write_text(
        "def add(a, b):\n    return a + b\n",
        encoding="utf-8",
    )
    (tmp_path / "benchmark" / "example.py").write_text(
        "def add(a, b):\n    return a - b\n",
        encoding="utf-8",
    )

    test_file = tmp_path / "tests" / "test_calc.py"
    test_file.write_text(
        "from app.calculator import add\n\n"
        "def test_add():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )

    result = resolve_imported_function(
        test_file=test_file,
        function_name="add",
        root=tmp_path,
    )

    assert result == [(tmp_path / "app" / "calculator.py").resolve()]


def test_unimported_function_is_not_guessed(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "app").mkdir()

    (tmp_path / "app" / "calculator.py").write_text(
        "def add(a, b):\n    return a + b\n",
        encoding="utf-8",
    )

    test_file = tmp_path / "tests" / "test_calc.py"
    test_file.write_text(
        "def test_add():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )

    result = resolve_imported_function(
        test_file=test_file,
        function_name="add",
        root=tmp_path,
    )

    assert result == []
