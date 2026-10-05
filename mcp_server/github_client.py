import os
import requests
from dotenv import load_dotenv

load_dotenv()

OWNER = "gagneshkakkar"
REPO = "mcp-devops-research"

BASE_URL = f"https://api.github.com/repos/{OWNER}/{REPO}"


def get_headers():
    """Return headers required for GitHub API requests."""
    token = os.getenv("GITHUB_TOKEN")

    if not token:
        raise RuntimeError("GITHUB_TOKEN environment variable is not set.")

    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10",
    }


def get_workflow_runs(limit: int = 5):
    """Get recent GitHub Actions workflow runs."""

    response = requests.get(
        f"{BASE_URL}/actions/runs",
        headers=get_headers(),
        params={"per_page": limit},
        timeout=30,
    )

    response.raise_for_status()

    return response.json()["workflow_runs"]


def get_workflow_run(run_id: int):
    """Get details of a specific workflow run."""

    response = requests.get(
        f"{BASE_URL}/actions/runs/{run_id}",
        headers=get_headers(),
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


def get_workflow_jobs(run_id: int):
    """Get jobs belonging to a workflow run."""

    response = requests.get(
        f"{BASE_URL}/actions/runs/{run_id}/jobs",
        headers=get_headers(),
        params={"per_page": 100},
        timeout=30,
    )

    response.raise_for_status()

    return response.json()["jobs"]


def get_workflow_logs(run_id: int):
    """Download workflow logs as raw ZIP bytes."""

    response = requests.get(
        f"{BASE_URL}/actions/runs/{run_id}/logs",
        headers=get_headers(),
        timeout=60,
    )

    response.raise_for_status()

    return response.content