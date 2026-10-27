import subprocess
from pathlib import Path
from datetime import datetime


def run_git_command(
    args: list[str]
) -> tuple[bool, str]:
    """
    Run a Git command and return:
    (success, output)
    """

    result = subprocess.run(
        ["git"] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace"
    )

    output = (
        result.stdout.strip()
        if result.stdout.strip()
        else result.stderr.strip()
    )

    return (
        result.returncode == 0,
        output
    )


def get_current_branch() -> str:
    """
    Return the current Git branch name.
    """

    success, output = run_git_command(
        ["branch", "--show-current"]
    )

    if not success:
        raise RuntimeError(
            f"Unable to determine current branch: {output}"
        )

    return output


def create_repair_branch(
    run_id: int
) -> str:
    """
    Create a unique repair branch from the current branch.
    """

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    branch_name = (
        f"auto-repair/run-{run_id}-{timestamp}"
    )

    success, output = run_git_command(
        [
            "switch",
            "-c",
            branch_name
        ]
    )

    if not success:
        raise RuntimeError(
            f"Unable to create repair branch: {output}"
        )

    return branch_name


def get_status() -> str:
    """
    Return the current Git status.
    """

    success, output = run_git_command(
        ["status", "--short"]
    )

    if not success:
        raise RuntimeError(
            f"Unable to retrieve Git status: {output}"
        )

    return output


def commit_changes(
    message: str,
    files: list[str] | None = None,
) -> str:
    """Stage only explicitly approved files and create a commit."""

    if not files:
        raise ValueError(
            "An explicit non-empty file list is required."
        )

    unique_files = _validate_repository_files(files)

    success, output = run_git_command(
        ["add", "--", *unique_files]
    )
    if not success:
        raise RuntimeError(f"Git add failed: {output}")

    success, output = run_git_command(
        ["commit", "-m", message]
    )
    if not success:
        raise RuntimeError(f"Git commit failed: {output}")

    return output

def push_branch(
    branch_name: str
) -> str:
    """
    Push a repair branch to the GitHub remote.
    """

    success, output = run_git_command(
        [
            "push",
            "-u",
            "origin",
            branch_name
        ]
    )

    if not success:
        raise RuntimeError(
            f"Git push failed: {output}"
        )

    return output

if __name__ == "__main__":

    print(
        "========== GIT MANAGER TEST =========="
    )

    print(
        f"Current branch: {get_current_branch()}"
    )

    print(
        "Git status:"
    )

    status = get_status()

    if status:
        print(status)
    else:
        print(
            "Working tree clean."
        )

def create_pull_request(
    head_branch: str,
    base_branch: str = "main",
    title: str | None = None,
    body: str | None = None
) -> dict:
    """
    Create a GitHub Pull Request for an autonomous repair branch.
    """

    from mcp_server.github_client import (
        create_pull_request as github_create_pull_request
    )

    return github_create_pull_request(
        head_branch=head_branch,
        base_branch=base_branch,
        title=title,
        body=body
    )

def _validate_repository_files(files: list[str]) -> list[str]:
    """Validate paths and return repository-relative file paths."""

    from pathlib import Path

    # Reject obviously unsafe paths before invoking Git.
    for file_path in files:
        if not isinstance(file_path, str) or not file_path.strip():
            raise ValueError(
                "Every staged file path must be a non-empty string."
            )

        supplied_path = Path(file_path)

        if supplied_path.is_absolute():
            raise ValueError(
                f"File path must be relative to the repository: {file_path}"
            )

        if ".." in supplied_path.parts:
            raise ValueError(
                f"File path escapes the repository: {file_path}"
            )

    success, output = run_git_command(
        ["rev-parse", "--show-toplevel"]
    )
    if not success or not output:
        raise RuntimeError(
            f"Unable to determine Git repository root: {output}"
        )

    repository_root = Path(output).resolve()
    validated_files = []

    for file_path in files:
        resolved_path = (repository_root / Path(file_path)).resolve()

        try:
            relative_path = resolved_path.relative_to(repository_root)
        except ValueError as exc:
            raise ValueError(
                f"File path escapes the repository: {file_path}"
            ) from exc

        if relative_path == Path("."):
            raise ValueError(
                f"A directory-wide staging path is not allowed: {file_path}"
            )

        if not resolved_path.exists():
            raise ValueError(f"File does not exist: {file_path}")

        if not resolved_path.is_file():
            raise ValueError(f"Path is not a regular file: {file_path}")

        validated_files.append(relative_path.as_posix())

    return list(dict.fromkeys(validated_files))
