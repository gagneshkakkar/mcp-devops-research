import asyncio
from types import SimpleNamespace

import pytest

from agents import diagnosis_agent


SHA = "961a28199f01a5acf5383ca8d1dfe0fb02cc8281"


class FakeClientSession:
    async def initialize(self):
        return None

    async def call_tool(self, name, arguments=None):
        if name == "get_build_status":
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        text=f"Run ID: 8\nCommit SHA: {SHA}\n"
                    )
                ]
            )

        if name == "get_build_logs":
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        text=(
                            "FAILED tests/test_project.py::test_multiply\n"
                            "E assert 7 == 12\n"
                            "AssertionError"
                        )
                    )
                ]
            )

        if name == "get_repository_file_tool":
            assert arguments["ref"] == SHA
            return SimpleNamespace(
                isError=False,
                content=[
                    SimpleNamespace(
                        text=(
                            "REPOSITORY_FILE_NOT_FOUND: "
                            + arguments["path"]
                        )
                    )
                ],
            )

        pytest.fail(f"Unexpected MCP tool call: {name}")


class FakeClientSessionContext:
    def __init__(self, *args, **kwargs):
        self.session = FakeClientSession()

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeStdioContext:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return object(), object()

    async def __aexit__(self, exc_type, exc, traceback):
        return False


def test_missing_historical_test_source_stops_before_llm(monkeypatch):
    llm_calls = []

    def forbidden_llm(prompt):
        llm_calls.append(prompt)
        pytest.fail("LLM must not run when historical source is missing.")

    monkeypatch.setattr(
        diagnosis_agent,
        "stdio_client",
        lambda *args, **kwargs: FakeStdioContext(),
    )
    monkeypatch.setattr(
        diagnosis_agent,
        "ClientSession",
        FakeClientSessionContext,
    )
    monkeypatch.setattr(diagnosis_agent, "ask_llm", forbidden_llm)

    with pytest.raises(FileNotFoundError, match="Historical file not found"):
        asyncio.run(diagnosis_agent.diagnose_run(run_id=8))

    assert llm_calls == []
