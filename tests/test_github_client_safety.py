import base64

import pytest

from mcp_server import github_client


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


def test_repository_file_uses_exact_commit_sha(monkeypatch):
    historical_source = "def multiply(a, b):\n    return a + b\n"
    encoded = base64.b64encode(
        historical_source.encode("utf-8")
    ).decode("ascii")

    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse({
            "type": "file",
            "content": encoded,
        })

    monkeypatch.setattr(github_client.requests, "get", fake_get)
    monkeypatch.setattr(
        github_client,
        "get_headers",
        lambda: {"Accept": "application/vnd.github+json"},
    )

    commit_sha = "961a28199f01a5acf5383ca8d1dfe0fb02cc8281"
    result = github_client.get_repository_file(
        "app/calculator.py",
        commit_sha,
    )

    assert result == historical_source
    assert captured["params"]["ref"] == commit_sha
    assert captured["url"].endswith("/contents/app/calculator.py")
    assert captured["timeout"] == 30


def test_repository_file_rejects_parent_traversal():
    with pytest.raises(ValueError, match="Invalid repository file path"):
        github_client.get_repository_file("../.env", "main")


def test_repository_file_rejects_non_file_response(monkeypatch):
    monkeypatch.setattr(
        github_client.requests,
        "get",
        lambda *args, **kwargs: FakeResponse({
            "type": "dir",
            "content": "",
        }),
    )
    monkeypatch.setattr(
        github_client,
        "get_headers",
        lambda: {},
    )

    with pytest.raises(ValueError, match="did not return a file"):
        github_client.get_repository_file("app", "main")
