import pytest

from agents.diagnosis_agent import extract_commit_sha


VALID_SHA = "961a28199f01a5acf5383ca8d1dfe0fb02cc8281"


def test_extracts_commit_sha():
    status = f"Run ID: 8\nCommit SHA: {VALID_SHA}\n"

    assert extract_commit_sha(status) == VALID_SHA


def test_normalizes_uppercase_commit_sha():
    status = f"Commit SHA: {VALID_SHA.upper()}"

    assert extract_commit_sha(status) == VALID_SHA


@pytest.mark.parametrize(
    "status",
    [
        "Run ID: 8",
        "Commit SHA: abc123",
        f"Commit SHA: {VALID_SHA[:-1]}",
        f"Commit SHA: {VALID_SHA}extra",
    ],
)
def test_rejects_missing_or_invalid_commit_sha(status):
    with pytest.raises(ValueError, match="40-character Commit SHA"):
        extract_commit_sha(status)
