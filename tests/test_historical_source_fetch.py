import asyncio
from types import SimpleNamespace

import pytest

from agents.diagnosis_agent import fetch_historical_source


class FakeSession:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return self.result


def test_fetches_source_at_exact_commit():
    sha = "961a28199f01a5acf5383ca8d1dfe0fb02cc8281"
    source = "def multiply(a, b):\n    return a + b\n"
    session = FakeSession(
        SimpleNamespace(
            isError=False,
            content=[SimpleNamespace(text=source)],
        )
    )

    result = asyncio.run(
        fetch_historical_source(session, "app/calculator.py", sha)
    )

    assert result == source
    assert session.calls == [
        (
            "get_repository_file_tool",
            {"path": "app/calculator.py", "ref": sha},
        )
    ]


def test_rejects_mcp_tool_error():
    session = FakeSession(
        SimpleNamespace(
            isError=True,
            content=[SimpleNamespace(text="Request failed")],
        )
    )

    with pytest.raises(RuntimeError, match="retrieval failed"):
        asyncio.run(
            fetch_historical_source(
                session,
                "app/calculator.py",
                "961a28199f01a5acf5383ca8d1dfe0fb02cc8281",
            )
        )


def test_rejects_error_text_and_empty_source():
    sha = "961a28199f01a5acf5383ca8d1dfe0fb02cc8281"

    for text in (
        "Error retrieving repository file at ref",
        "   ",
    ):
        session = FakeSession(
            SimpleNamespace(
                isError=False,
                content=[SimpleNamespace(text=text)],
            )
        )

        with pytest.raises(RuntimeError):
            asyncio.run(
                fetch_historical_source(
                    session,
                    "app/calculator.py",
                    sha,
                )
            )
