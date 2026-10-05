import subprocess
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
    message: str
) -> str:
    """
    Stage all tracked/untracked project changes
    and create a commit.
    """

    success, output = run_git_command(
        ["add", "."]
    )

    if not success:
        raise RuntimeError(
            f"Git add failed: {output}"
        )

    success, output = run_git_command(
        [
            "commit",
            "-m",
            message
        ]
    )

    if not success:
        raise RuntimeError(
            f"Git commit failed: {output}"
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