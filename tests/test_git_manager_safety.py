import pytest

from agents import git_manager


def test_commit_changes_requires_explicit_file_list():
    with pytest.raises(ValueError, match="file"):
        git_manager.commit_changes("test commit")


def test_commit_changes_stages_only_supplied_files(monkeypatch):
    commands = []

    def fake_run_git_command(args):
        commands.append(args)
        if args[0] == "add":
            return True, "files staged"
        if args[0] == "commit":
            return True, "commit created"
        return False, "unexpected command"

    monkeypatch.setattr(
        git_manager,
        "run_git_command",
        fake_run_git_command,
    )

    git_manager.commit_changes(
        "test commit",
        files=["app/calculator.py", "tests/test_project.py"],
    )

    assert commands == [
        ["add", "--", "app/calculator.py", "tests/test_project.py"],
        ["commit", "-m", "test commit"],
    ]
