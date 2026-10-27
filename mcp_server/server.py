import io
import os
import zipfile

from mcp.server import MCPServer

from mcp_server.github_client import (
    get_workflow_runs,
    get_workflow_run,
    get_workflow_jobs,
    get_workflow_logs,
    get_repository_file,
)

mcp = MCPServer("DevOps Research MCP Server")


@mcp.tool()
def read_file(file_path: str) -> str:
    """Read a text file from the project."""

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return file.read()

    except FileNotFoundError:
        return f"File not found: {file_path}"

    except Exception as error:
        return f"Error reading file: {error}"


@mcp.tool()
def get_build_status(run_id: int | None = None) -> str:
    """Get the status of a GitHub Actions workflow run."""

    try:
        if run_id is None:
            runs = get_workflow_runs(limit=5)

            if not runs:
                return "No workflow runs found."

            run = runs[0]

        else:
            run = get_workflow_run(run_id)

        return (
            f"Run #{run['run_number']}\n"
            f"Run ID: {run['id']}\n"
            f"Workflow: {run['name']}\n"
            f"Status: {run['status']}\n"
            f"Conclusion: {run['conclusion']}\n"
            f"Branch: {run['head_branch']}\n"
            f"Event: {run['event']}\n"
            f"Commit SHA: {run['head_sha']}"
        )

    except Exception as error:
        return f"Error retrieving build status: {error}"


@mcp.tool()
def get_build_logs(run_id: int | None = None) -> str:
    """Get logs from a GitHub Actions workflow run."""

    try:
        if run_id is None:
            runs = get_workflow_runs(limit=5)

            if not runs:
                return "No workflow runs found."

            run_id = runs[0]["id"]

        logs_zip = get_workflow_logs(run_id)

        logs = []

        with zipfile.ZipFile(io.BytesIO(logs_zip)) as archive:

            for filename in archive.namelist():

                if filename.endswith(".txt"):

                    content = archive.read(filename).decode(
                        "utf-8",
                        errors="replace"
                    )

                    logs.append(
                        f"\n===== {filename} =====\n"
                        f"{content}"
                    )

        return "\n".join(logs)

    except Exception as error:
        return f"Error retrieving build logs: {error}"


@mcp.tool()
def get_repository_file_tool(path: str, ref: str) -> str:
    """Read a repository file at a Git ref, with categorized errors."""
    import requests

    try:
        return get_repository_file(path, ref)
    except requests.HTTPError as error:
        response = error.response
        status_code = response.status_code if response is not None else None

        if status_code == 404:
            return f"REPOSITORY_FILE_NOT_FOUND: {path}"

        return (
            "REPOSITORY_FILE_HTTP_ERROR: "
            f"status={status_code}; retrieval failed."
        )
    except Exception as error:
        # Avoid returning tokens, headers, or arbitrary exception details.
        return (
            "REPOSITORY_FILE_RETRIEVAL_ERROR: "
            f"{type(error).__name__}; retrieval failed."
        )


if __name__ == "__main__":
    mcp.run()