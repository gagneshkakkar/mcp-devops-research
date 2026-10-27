import asyncio
from types import SimpleNamespace

import pytest

from agents.diagnosis_agent import locate_historical_implementation_targets


SHA = "961a28199f01a5acf5383ca8d1dfe0fb02cc8281"

TEST_SOURCE = (
    "\ufefffrom app.calculator import multiply\n"
    "def test_multiply():\n"
    "    assert multiply(4, 3) == 12\n"
)

IMPLEMENTATION_SOURCE = (
    "def multiply(a, b):\n"
    "    return a + b\n"
)


class FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        path = arguments["path"]
        response = self.responses[path]

        if isinstance(response, Exception):
            raise response

        return SimpleNamespace(
            isError=False,
            content=[SimpleNamespace(text=response)],
        )


def test_resolves_unique_historical_implementation():
    session = FakeSession({
        "app/calculator.py": IMPLEMENTATION_SOURCE,
        "app/calculator/__init__.py": (
            "REPOSITORY_FILE_NOT_FOUND: app/calculator/__init__.py"
        ),
    })

    targets = asyncio.run(
        locate_historical_implementation_targets(
            session,
            "tests/test_project.py::test_multiply",
            TEST_SOURCE,
            SHA,
        )
    )

    assert targets == [
        {"file": "app/calculator.py", "function": "multiply"}
    ]
    assert all(call[1]["ref"] == SHA for call in session.calls)


def test_rejects_ambiguous_historical_implementation():
    session = FakeSession({
        "app/calculator.py": IMPLEMENTATION_SOURCE,
        "app/calculator/__init__.py": "def multiply(a, b): return a * b\n",
    })

    with pytest.raises(RuntimeError, match="Ambiguous historical implementation"):
        asyncio.run(
            locate_historical_implementation_targets(
                session,
                "tests/test_project.py::test_multiply",
                TEST_SOURCE,
                SHA,
            )
        )


def test_stops_on_historical_retrieval_error():
    session = FakeSession({
        "app/calculator.py": (
            "REPOSITORY_FILE_HTTP_ERROR: status=401; retrieval failed."
        ),
        "app/calculator/__init__.py": (
            "REPOSITORY_FILE_NOT_FOUND: app/calculator/__init__.py"
        ),
    })

    with pytest.raises(RuntimeError, match="retrieval failed"):
        asyncio.run(
            locate_historical_implementation_targets(
                session,
                "tests/test_project.py::test_multiply",
                TEST_SOURCE,
                SHA,
            )
        )
