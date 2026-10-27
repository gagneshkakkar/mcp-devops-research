import pytest

from agents import orchestrator


@pytest.mark.anyio
async def test_review_required_stops_before_branch_creation(monkeypatch):
    diagnosis = {
        "test": "tests/test_project.py::test_add",
        "file": "app/calculator.py",
        "function": "add",
        "actual": "5",
        "expected": "6",
        "root_cause": "The failure needs review.",
        "recommended_fix": "Review the test and implementation.",
        "review_status": "REVIEW_REQUIRED",
    }

    async def fake_diagnose_run(run_id=None):
        return {
            "run_id": 123,
            "diagnosis": {"diagnoses": [diagnosis]},
            "failure_contexts": [],
            "implementation_source": {},
        }

    def forbidden_action(*args, **kwargs):
        pytest.fail("A repair action ran despite REVIEW_REQUIRED")

    monkeypatch.setattr(orchestrator, "diagnose_run", fake_diagnose_run)
    monkeypatch.setattr(orchestrator, "create_repair_branch", forbidden_action)
    monkeypatch.setattr(orchestrator, "process_diagnosis", forbidden_action)

    result = await orchestrator.run_autonomous_repair(123)

    assert result["overall_success"] is False
    assert result["repair_branch"] is None
    assert result["repair_results"] == []
    assert result["review_required"] is True

def test_target_validation_preserves_valid_review_statuses():
    from agents.diagnosis_agent import validate_diagnosis_targets

    failure_contexts = [
        {
            "test": "tests/test_project.py::test_add",
            "implementation_targets": [
                {
                    "file": "app/calculator.py",
                    "function": "add",
                }
            ],
        }
    ]

    for status in ("READY_FOR_VALIDATION", "REVIEW_REQUIRED"):
        diagnosis = {
            "diagnoses": [
                {
                    "test": "tests/test_project.py::test_add",
                    "actual": "5",
                    "expected": "6",
                    "root_cause": "The evidence is inconclusive.",
                    "file": "app/calculator.py",
                    "function": "add",
                    "recommended_fix": "Review the test and implementation.",
                    "review_status": status,
                }
            ]
        }

        result = validate_diagnosis_targets(diagnosis, failure_contexts)
        assert result["diagnoses"][0]["review_status"] == status


def test_target_validation_defaults_invalid_review_status_to_review():
    from agents.diagnosis_agent import validate_diagnosis_targets

    failure_contexts = [
        {
            "test": "tests/test_project.py::test_add",
            "implementation_targets": [
                {
                    "file": "app/calculator.py",
                    "function": "add",
                }
            ],
        }
    ]

    for status in (None, "APPROVED", "UNKNOWN"):
        item = {
            "test": "tests/test_project.py::test_add",
            "actual": "5",
            "expected": "6",
            "root_cause": "The evidence is inconclusive.",
            "file": "app/calculator.py",
            "function": "add",
            "recommended_fix": "Review the test and implementation.",
        }
        if status is not None:
            item["review_status"] = status

        diagnosis = {"diagnoses": [item]}
        result = validate_diagnosis_targets(diagnosis, failure_contexts)

        assert result["diagnoses"][0]["review_status"] == "REVIEW_REQUIRED"


@pytest.mark.anyio
async def test_branch_creation_failure_stops_before_repair_or_publication(monkeypatch):
    diagnosis = {
        "test": "tests/test_project.py::test_add",
        "file": "app/calculator.py",
        "function": "add",
        "actual": "5",
        "expected": "6",
        "root_cause": "The failure needs review.",
        "recommended_fix": "Review the test and implementation.",
        "review_status": "READY_FOR_VALIDATION",
    }

    async def fake_diagnose_run(run_id=None):
        return {
            "run_id": 123,
            "diagnosis": {"diagnoses": [diagnosis]},
            "failure_contexts": [
                {
                    "test": diagnosis["test"],
                    "implementation_targets": [
                        {
                            "file": diagnosis["file"],
                            "function": diagnosis["function"],
                        }
                    ],
                }
            ],
            "implementation_source": {
                diagnosis["file"]: (
                    "def add(a, b):\n    return a + b\n\n"
                    "def subtract(a, b):\n    return a - b\n"
                )
            },
        }

    def fail_branch_creation(run_id):
        raise RuntimeError("simulated branch creation failure")

    def forbidden_action(*args, **kwargs):
        pytest.fail("Repair or publication ran after branch creation failed")

    monkeypatch.setattr(orchestrator, "diagnose_run", fake_diagnose_run)
    monkeypatch.setattr(orchestrator, "create_repair_branch", fail_branch_creation)
    monkeypatch.setattr(orchestrator, "process_diagnosis", forbidden_action)
    monkeypatch.setattr(orchestrator, "commit_changes", forbidden_action)
    monkeypatch.setattr(orchestrator, "push_branch", forbidden_action)
    monkeypatch.setattr(orchestrator, "create_pull_request", forbidden_action)

    with pytest.raises(RuntimeError, match="simulated branch creation failure"):
        await orchestrator.run_autonomous_repair(123)

@pytest.mark.anyio
@pytest.mark.parametrize("status", [None, "APPROVED", "UNKNOWN"])
async def test_invalid_review_status_stops_before_branch_creation(
    monkeypatch, status
):
    diagnosis = {
        "test": "tests/test_project.py::test_add",
        "file": "app/calculator.py",
        "function": "add",
        "actual": "5",
        "expected": "6",
        "root_cause": "The evidence is inconclusive.",
        "recommended_fix": "Review the implementation and test.",
    }
    if status is not None:
        diagnosis["review_status"] = status

    async def fake_diagnose_run(run_id=None):
        return {
            "run_id": 123,
            "diagnosis": {"diagnoses": [diagnosis]},
            "failure_contexts": [],
            "implementation_source": {},
        }

    def forbidden_action(*args, **kwargs):
        pytest.fail("Unsafe action ran for an invalid review status")

    monkeypatch.setattr(orchestrator, "diagnose_run", fake_diagnose_run)
    monkeypatch.setattr(orchestrator, "create_repair_branch", forbidden_action)
    monkeypatch.setattr(orchestrator, "process_diagnosis", forbidden_action)
    monkeypatch.setattr(orchestrator, "commit_changes", forbidden_action)
    monkeypatch.setattr(orchestrator, "push_branch", forbidden_action)
    monkeypatch.setattr(orchestrator, "create_pull_request", forbidden_action)

    result = await orchestrator.run_autonomous_repair(123)

    assert result["overall_success"] is False
    assert result["repair_branch"] is None
    assert result["repair_results"] == []
    assert result["review_required"] is True

@pytest.mark.anyio
@pytest.mark.parametrize("rollback_result", [True, False])
async def test_final_validation_failure_reports_rollback_and_never_publishes(
    monkeypatch, rollback_result
):
    diagnosis = {
        "test": "tests/test_project.py::test_add",
        "file": "app/calculator.py",
        "function": "add",
        "actual": "5",
        "expected": "6",
        "root_cause": "Simulated implementation defect.",
        "recommended_fix": "Correct the implementation.",
        "review_status": "READY_FOR_VALIDATION",
    }

    async def fake_diagnose_run(run_id=None):
        return {
            "run_id": 123,
            "diagnosis": {"diagnoses": [diagnosis]},
            "failure_contexts": [
                {
                    "test": diagnosis["test"],
                    "implementation_targets": [
                        {
                            "file": diagnosis["file"],
                            "function": diagnosis["function"],
                        }
                    ],
                }
            ],
            "implementation_source": {
                diagnosis["file"]: (
                    "def add(a, b):\n    return a + b\n\n"
                    "def subtract(a, b):\n    return a - b\n"
                )
            },
        }

    def fake_process_diagnosis(diagnosis, implementation_source):
        return {
            "success": True,
            "test": diagnosis["test"],
            "file": diagnosis["file"],
            "function": diagnosis["function"],
            "backup": "mock-backup",
        }

    def forbidden_publication(*args, **kwargs):
        pytest.fail("Publication ran despite failed final validation")

    rollback_calls = []

    def fake_rollback(repair_results):
        rollback_calls.append(repair_results)
        return rollback_result

    monkeypatch.setattr(orchestrator, "diagnose_run", fake_diagnose_run)
    monkeypatch.setattr(
        orchestrator, "create_repair_branch", lambda run_id: "test-repair-branch"
    )
    monkeypatch.setattr(
        orchestrator, "process_diagnosis", fake_process_diagnosis
    )
    monkeypatch.setattr(
        orchestrator, "run_tests", lambda: (False, "simulated test failure")
    )
    monkeypatch.setattr(
        orchestrator, "rollback_all_repairs", fake_rollback
    )
    monkeypatch.setattr(orchestrator, "commit_changes", forbidden_publication)
    monkeypatch.setattr(orchestrator, "push_branch", forbidden_publication)
    monkeypatch.setattr(
        orchestrator, "create_pull_request", forbidden_publication
    )

    result = await orchestrator.run_autonomous_repair(123)

    assert result["overall_success"] is False
    assert result["final_tests_passed"] is False
    assert result["final_test_output"] == "simulated test failure"
    assert len(rollback_calls) == 1
    assert result["rollback_success"] is rollback_result




@pytest.mark.anyio
async def test_commit_failure_stops_push_and_pull_request(monkeypatch):
    diagnosis = {
        "test": "tests/test_project.py::test_add",
        "file": "app/calculator.py",
        "function": "add",
        "actual": "5",
        "expected": "6",
        "root_cause": "Simulated implementation defect.",
        "recommended_fix": "Correct the implementation.",
        "review_status": "READY_FOR_VALIDATION",
    }

    async def fake_diagnose_run(run_id=None):
        return {
            "run_id": 123,
            "diagnosis": {"diagnoses": [diagnosis]},
            "failure_contexts": [
                {
                    "test": diagnosis["test"],
                    "implementation_targets": [
                        {
                            "file": diagnosis["file"],
                            "function": diagnosis["function"],
                        }
                    ],
                }
            ],
            "implementation_source": {
                diagnosis["file"]: (
                    "def add(a, b):\n    return a + b\n\n"
                    "def subtract(a, b):\n    return a - b\n"
                )
            },
        }

    def fake_process_diagnosis(diagnosis, implementation_source):
        return {
            "success": True,
            "test": diagnosis["test"],
            "file": diagnosis["file"],
            "function": diagnosis["function"],
            "backup": "mock-backup",
        }

    def fail_commit(message, files=None):
        raise RuntimeError("simulated commit failure")

    def forbidden_action(*args, **kwargs):
        pytest.fail("Push or PR creation ran after commit failure")

    monkeypatch.setattr(orchestrator, "diagnose_run", fake_diagnose_run)
    monkeypatch.setattr(
        orchestrator, "create_repair_branch",
        lambda run_id: "test-repair-branch",
    )
    monkeypatch.setattr(
        orchestrator, "process_diagnosis", fake_process_diagnosis
    )
    monkeypatch.setattr(
        orchestrator, "run_tests", lambda: (True, "all tests passed")
    )
    monkeypatch.setattr(orchestrator, "commit_changes", fail_commit)
    monkeypatch.setattr(orchestrator, "push_branch", forbidden_action)
    monkeypatch.setattr(
        orchestrator, "create_pull_request", forbidden_action
    )

    result = await orchestrator.run_autonomous_repair(123)

    assert result["publication_status"] == "FAILED"
    assert result["publication_error"] == (
        "Publication failed during COMMITTING: RuntimeError"
    )
    assert result["overall_success"] is False
    assert result["pull_request"] is None


@pytest.mark.anyio
async def test_push_failure_stops_pull_request(monkeypatch):
    diagnosis = {
        "test": "tests/test_project.py::test_add",
        "file": "app/calculator.py",
        "function": "add",
        "actual": "5",
        "expected": "6",
        "root_cause": "Simulated implementation defect.",
        "recommended_fix": "Correct the implementation.",
        "review_status": "READY_FOR_VALIDATION",
    }

    async def fake_diagnose_run(run_id=None):
        return {
            "run_id": 123,
            "diagnosis": {"diagnoses": [diagnosis]},
            "failure_contexts": [
                {
                    "test": diagnosis["test"],
                    "implementation_targets": [
                        {
                            "file": diagnosis["file"],
                            "function": diagnosis["function"],
                        }
                    ],
                }
            ],
            "implementation_source": {
                diagnosis["file"]: (
                    "def add(a, b):\n    return a + b\n\n"
                    "def subtract(a, b):\n    return a - b\n"
                )
            },
        }

    def fake_process_diagnosis(diagnosis, implementation_source):
        return {
            "success": True,
            "test": diagnosis["test"],
            "file": diagnosis["file"],
            "function": diagnosis["function"],
            "backup": "mock-backup",
        }

    def fake_push(branch):
        raise RuntimeError("simulated push failure")

    def forbidden_pr(*args, **kwargs):
        pytest.fail("Pull-request creation ran after push failure")

    monkeypatch.setattr(orchestrator, "diagnose_run", fake_diagnose_run)
    monkeypatch.setattr(
        orchestrator, "create_repair_branch",
        lambda run_id: "test-repair-branch",
    )
    monkeypatch.setattr(
        orchestrator, "process_diagnosis", fake_process_diagnosis
    )
    monkeypatch.setattr(
        orchestrator, "run_tests", lambda: (True, "all tests passed")
    )
    monkeypatch.setattr(
        orchestrator, "commit_changes",
        lambda message, files=None: "mock-commit",
    )
    monkeypatch.setattr(orchestrator, "push_branch", fake_push)
    monkeypatch.setattr(
        orchestrator, "create_pull_request", forbidden_pr
    )

    result = await orchestrator.run_autonomous_repair(123)

    assert result["publication_status"] == "FAILED"
    assert result["publication_error"] == (
        "Publication failed during PUSHING: RuntimeError"
    )
    assert result["overall_success"] is False
    assert result["pull_request"] is None



def test_rollback_repair_restores_original_file(tmp_path):
    target = tmp_path / "calculator.py"
    backup = tmp_path / "calculator.py.bak"

    backup.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    target.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

    result = orchestrator.rollback_repair(str(target), str(backup))

    assert result is True
    assert target.read_text(encoding="utf-8") == (
        "def add(a, b):\n    return a + b\n"
    )


def test_rollback_all_repairs_uses_reverse_order(monkeypatch):
    rollback_order = []

    def fake_rollback(file_path, backup_path):
        rollback_order.append(file_path)
        return True


    monkeypatch.setattr(orchestrator, "rollback_repair", fake_rollback)

    repairs = [
        {"success": True, "file": "first.py", "backup": "first.bak"},
        {"success": True, "file": "second.py", "backup": "second.bak"},
        {"success": True, "file": "third.py", "backup": "third.bak"},
    ]

    result = orchestrator.rollback_all_repairs(repairs)

    assert result is True
    assert rollback_order == ["third.py", "second.py", "first.py"]



@pytest.mark.anyio
async def test_publication_stages_only_unique_successful_repair_files(monkeypatch):
    diagnoses = [
        {
            "test": "tests/test_project.py::test_add",
            "file": "app/calculator.py",
            "function": "add",
            "actual": "5",
            "expected": "6",
            "root_cause": "Simulated defect.",
            "recommended_fix": "Correct implementation.",
            "review_status": "READY_FOR_VALIDATION",
        },
        {
            "test": "tests/test_project.py::test_subtract",
            "file": "app/calculator.py",
            "function": "subtract",
            "actual": "1",
            "expected": "2",
            "root_cause": "Simulated defect.",
            "recommended_fix": "Correct implementation.",
            "review_status": "READY_FOR_VALIDATION",
        },
    ]

    async def fake_diagnose_run(run_id=None):
        return {
            "run_id": 123,
            "diagnosis": {"diagnoses": diagnoses},
            "failure_contexts": [
                {
                    "test": diagnosis["test"],
                    "implementation_targets": [
                        {
                            "file": diagnosis["file"],
                            "function": diagnosis["function"],
                        }
                    ],
                }
                for diagnosis in diagnoses
            ],
            "implementation_source": {
                "app/calculator.py": (
                    "def add(a, b):\n    return a + b\n\n"
                    "def subtract(a, b):\n    return a - b\n"
                )
            },
        }

    def fake_process_diagnosis(diagnosis, implementation_source):
        return {
            "success": True,
            "test": diagnosis["test"],
            "file": diagnosis["file"],
            "function": diagnosis["function"],
            "backup": "mock-backup",
        }

    captured = {}

    def fake_commit(message, files=None):
        captured["message"] = message
        captured["files"] = files
        return "mock commit"

    monkeypatch.setattr(orchestrator, "diagnose_run", fake_diagnose_run)
    monkeypatch.setattr(
        orchestrator, "create_repair_branch", lambda run_id: "test-repair-branch"
    )
    monkeypatch.setattr(
        orchestrator, "process_diagnosis", fake_process_diagnosis
    )
    monkeypatch.setattr(
        orchestrator, "run_tests", lambda: (True, "all tests passed")
    )
    monkeypatch.setattr(orchestrator, "commit_changes", fake_commit)
    monkeypatch.setattr(
        orchestrator, "push_branch", lambda branch: "mock push"
    )
    monkeypatch.setattr(
        orchestrator,
        "create_pull_request",
        lambda **kwargs: {"number": 999, "url": "https://example.invalid/pr/999"},
    )

    await orchestrator.run_autonomous_repair(123)

    assert captured["files"] == ["app/calculator.py"]
