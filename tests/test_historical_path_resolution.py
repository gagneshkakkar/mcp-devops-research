import requests
import pytest

from mcp_server import github_client


def test_resolves_one_existing_historical_candidate(monkeypatch):
    calls = []

    def fake_get_repository_file(path, ref):
        calls.append((path, ref))
        if path == "app/calculator.py":
            return "def multiply(a, b): return a * b"
        response = requests.Response()
        response.status_code = 404
        error = requests.HTTPError("Not found", response=response)
        raise error

    monkeypatch.setattr(
        github_client,
        "get_repository_file",
        fake_get_repository_file,
    )

    sha = "961a28199f01a5acf5383ca8d1dfe0fb02cc8281"
    result = github_client.resolve_repository_file_path(
        ["app/calculator.py", "app/calculator/__init__.py"],
        sha,
    )

    assert result == "app/calculator.py"
    assert calls == [
        ("app/calculator.py", sha),
        ("app/calculator/__init__.py", sha),
    ]


def test_does_not_treat_authentication_failure_as_missing(monkeypatch):
    def fake_get_repository_file(path, ref):
        response = requests.Response()
        response.status_code = 401
        raise requests.HTTPError("Unauthorized", response=response)

    monkeypatch.setattr(
        github_client,
        "get_repository_file",
        fake_get_repository_file,
    )

    with pytest.raises(requests.HTTPError):
        github_client.resolve_repository_file_path(
            ["app/calculator.py"],
            "961a28199f01a5acf5383ca8d1dfe0fb02cc8281",
        )


def test_rejects_ambiguous_historical_candidates(monkeypatch):
    monkeypatch.setattr(
        github_client,
        "get_repository_file",
        lambda path, ref: "source",
    )

    with pytest.raises(ValueError, match="ambiguous or unavailable"):
        github_client.resolve_repository_file_path(
            ["app/calculator.py", "app/calculator/__init__.py"],
            "961a28199f01a5acf5383ca8d1dfe0fb02cc8281",
        )
