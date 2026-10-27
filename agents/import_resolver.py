import ast
from pathlib import Path


def resolve_imported_function(
    test_file: str | Path,
    function_name: str,
    root: str | Path = ".",
) -> list[Path]:
    """
    Resolve a function through explicit imports in a test module.

    Returns repository-relative paths for matching imported symbols.
    An empty list means the import could not be resolved confidently.
    Does not search unrelated files by function name.
    """
    root_path = Path(root).resolve()
    test_path = Path(test_file)

    if not test_path.is_absolute():
        test_path = root_path / test_path

    test_path = test_path.resolve()

    try:
        test_path.relative_to(root_path)
        source = test_path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
    except (OSError, ValueError, SyntaxError):
        return []

    module_names = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if any(alias.name == function_name for alias in node.names):
                if node.module:
                    module_names.add("." * node.level + node.module)

    if len(module_names) != 1:
        return []

    module_name = next(iter(module_names))

    # Resolve ordinary absolute imports only. Relative imports and
    # ambiguous cases remain unresolved rather than guessed.
    if module_name.startswith("."):
        return []

    module_parts = module_name.split(".")
    module_path = root_path.joinpath(*module_parts)

    candidates = [
        module_path.with_suffix(".py"),
        module_path / "__init__.py",
    ]

    existing = []
    for candidate in candidates:
        if candidate.is_file():
            resolved = candidate.resolve()
            try:
                resolved.relative_to(root_path)
            except ValueError:
                continue
            existing.append(resolved)

    # A single concrete module is required.
    if len(existing) != 1:
        return []

    return existing



def resolve_imported_function_from_source(
    test_source: str,
    function_name: str,
    root: str | Path = ".",
) -> list[str]:
    """
    Map an explicit absolute import in historical test source to a
    repository-relative module path.

    Does not require the implementation file to exist in the local tree;
    the returned path can be retrieved from the historical Git commit.
    Ambiguous or unsupported imports return an empty list.
    """
    try:
        tree = ast.parse(test_source.lstrip("\ufeff"))
    except (SyntaxError, TypeError):
        return []

    module_names = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue

        if not any(alias.name == function_name for alias in node.names):
            continue

        if node.level != 0 or not node.module:
            return []

        module_names.add(node.module)

    if len(module_names) != 1:
        return []

    module_name = next(iter(module_names))
    parts = module_name.split(".")

    if any(not part.isidentifier() for part in parts):
        return []

    module_path = "/".join(parts)

    # Return both possible module layouts only if callers can verify
    # which file exists at the historical commit.
    return [
        f"{module_path}.py",
        f"{module_path}/__init__.py",
    ]
