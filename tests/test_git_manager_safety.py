import pytest

from agents import git_manager


def test_commit_changes_requires_explicit_file_list():
    with pytest.raises(ValueError, match="file"):
        git_manager.commit_changes("test commit")


def test_commit_changes_stages_only_supplied_files(monkeypatch):
    commands = []

    def fake_run_git_command(args):
        commands.append(args)
        if args == ["rev-parse", "--show-toplevel"]:
            return True, str(git_manager.Path.cwd())
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
        ["rev-parse", "--show-toplevel"],
        ["add", "--", "app/calculator.py", "tests/test_project.py"],
        ["commit", "-m", "test commit"],
    ]

def test_commit_changes_rejects_parent_directory_path(monkeypatch):
    def unexpected_git_command(args):
        pytest.fail(f"Git must not run for an invalid path: {args}")

    monkeypatch.setattr(
        git_manager,
        "run_git_command",
        unexpected_git_command,
    )

    with pytest.raises(ValueError, match="repository"):
        git_manager.commit_changes(
            "test commit",
            files=["../outside.txt"],
        )


def test_commit_changes_rejects_absolute_path(monkeypatch, tmp_path):
    outside_file = tmp_path / "outside.txt"

    def unexpected_git_command(args):
        pytest.fail(f"Git must not run for an invalid path: {args}")

    monkeypatch.setattr(
        git_manager,
        "run_git_command",
        unexpected_git_command,
    )

    with pytest.raises(ValueError, match="repository"):
        git_manager.commit_changes(
            "test commit",
            files=[str(outside_file)],
        )
def test_commit_changes_rejects_nonexistent_file(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    monkeypatch.setattr(
        git_manager,
        "run_git_command",
        lambda args: (True, str(repo))
        if args == ["rev-parse", "--show-toplevel"]
        else pytest.fail(f"Unexpected Git command: {args}"),
    )

    with pytest.raises(ValueError, match="does not exist"):
        git_manager.commit_changes(
            "test commit",
            files=["missing.py"],
        )


def test_commit_changes_rejects_directory(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "folder").mkdir()

    monkeypatch.setattr(
        git_manager,
        "run_git_command",
        lambda args: (True, str(repo))
        if args == ["rev-parse", "--show-toplevel"]
        else pytest.fail(f"Unexpected Git command: {args}"),
    )

    with pytest.raises(ValueError, match="regular file"):
        git_manager.commit_changes(
            "test commit",
            files=["folder"],
        )


def test_commit_changes_rejects_symlink_escape(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    outside_file = tmp_path / "outside.py"
    outside_file.write_text("unsafe", encoding="utf-8")

    link = repo / "outside_link.py"

    try:
        link.symlink_to(outside_file)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation is not permitted on this system")

    monkeypatch.setattr(
        git_manager,
        "run_git_command",
        lambda args: (True, str(repo))
        if args == ["rev-parse", "--show-toplevel"]
        else pytest.fail(f"Unexpected Git command: {args}"),
    )

    with pytest.raises(ValueError, match="escapes the repository"):
        git_manager.commit_changes(
            "test commit",
            files=["outside_link.py"],
        )