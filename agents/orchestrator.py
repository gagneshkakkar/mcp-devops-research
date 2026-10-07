import subprocess
import sys
import re
import shutil
import anyio

from agents.diagnosis_agent import diagnose_run
from agents.repair_agent import generate_repair
from agents.repair_applier import apply_repair
from agents.repair_validator import validate_repair
from agents.git_manager import (
    create_repair_branch,
    commit_changes,
    push_branch,
    create_pull_request
)


MAX_REPAIR_ATTEMPTS = 3


# --------------------------------------------------
# Run tests
# --------------------------------------------------

def run_tests() -> tuple[bool, str]:
    """
    Run the project's pytest test suite.

    Returns:
        (success, output)
    """

    result = subprocess.run(
        [sys.executable, "-m", "pytest"],
        capture_output=True,
        text=True
    )

    output = (
        result.stdout
        + "\n"
        + result.stderr
    )

    print("\n========== TEST RESULTS ==========")
    print(output)

    return result.returncode == 0, output


# --------------------------------------------------
# Rollback one repair
# --------------------------------------------------

def rollback_repair(
    file_path: str,
    backup_path: str
) -> bool:
    """
    Restore a file from its backup.
    """

    try:

        shutil.copyfile(
            backup_path,
            file_path
        )

        print(
            f"Rollback successful: {file_path}"
        )

        return True

    except Exception as error:

        print(
            f"Rollback failed: {error}"
        )

        return False


# --------------------------------------------------
# Extract diagnosis target
# --------------------------------------------------

def extract_diagnosis_target(
    diagnosis: str
) -> tuple[str, str]:
    """
    Extract implementation file and function
    from an old-style text diagnosis.

    Kept for compatibility with previous versions.
    """

    file_match = re.search(
        r"Implementation File:\s*(.+)",
        diagnosis
    )

    function_match = re.search(
        r"Implementation Function:\s*(.+)",
        diagnosis
    )

    if not file_match:

        raise ValueError(
            "Could not identify implementation file."
        )

    if not function_match:

        raise ValueError(
            "Could not identify implementation function."
        )

    file_path = file_match.group(1).strip()
    function_name = function_match.group(1).strip()

    file_path = file_path.strip("`")
    function_name = function_name.strip("`")

    file_path = file_path.replace(
        "\\\\",
        "\\"
    )

    if function_name in {
        "N/A",
        "NA",
        "None",
        "Unknown"
    }:

        raise ValueError(
            "LLM did not identify a valid implementation function."
        )

    return file_path, function_name


# --------------------------------------------------
# Process one diagnosis
# --------------------------------------------------

def process_diagnosis(
    diagnosis: dict,
    implementation_source: str = ""
) -> dict:
    """
    Generate, validate and apply a repair for one
    structured diagnosis.

    Full pytest validation is performed only after
    all diagnoses have been processed.
    """

    test_name = diagnosis["test"]

    file_path = diagnosis["file"]

    function_name = diagnosis["function"]

    root_cause = diagnosis["root_cause"]

    recommended_fix = diagnosis["recommended_fix"]

    actual = diagnosis.get(
        "actual",
        ""
    )

    expected = diagnosis.get(
        "expected",
        ""
    )

    # --------------------------------------------------
    # Build diagnosis text
    # --------------------------------------------------

    diagnosis_text = f"""
Failed Test:
{test_name}

Actual Result:
{actual}

Expected Result:
{expected}

Root Cause:
{root_cause}

Recommended Fix:
{recommended_fix}

Implementation File:
{file_path}

Implementation Function:
{function_name}
"""

    print(
        "\n=========================================="
    )

    print(
        f"PROCESSING DIAGNOSIS: {test_name}"
    )

    print(
        "=========================================="
    )

    print(
        f"File: {file_path}"
    )

    print(
        f"Function: {function_name}"
    )

    print(
        f"Root Cause: {root_cause}"
    )

    # --------------------------------------------------
    # Repair generation
    # --------------------------------------------------

    print(
        "\n---------- REPAIR GENERATION ----------"
    )

    repair = generate_repair(
        diagnosis_text,
        file_path,
        function_name
    )

    print(
        f"Reason: {repair.get('reason')}"
    )

    print(
        f"Old Code: {repair.get('old_code')}"
    )

    print(
        f"New Code: {repair.get('new_code')}"
    )

    # --------------------------------------------------
    # Repair validation
    # --------------------------------------------------

    print(
        "\n---------- REPAIR VALIDATION ----------"
    )

    validation = validate_repair(
        diagnosis=diagnosis_text,
        file_path=file_path,
        function_name=function_name,
        old_code=repair["old_code"],
        new_code=repair["new_code"],
        implementation_source=implementation_source,
        failed_test=test_name,
        actual=actual,
        expected=expected
    )

    print(
        f"Approved: {validation['approved']}"
    )

    print(
        f"Reason: {validation['reason']}"
    )

    # --------------------------------------------------
    # Reject invalid repair
    # --------------------------------------------------

    if not validation["approved"]:

        print(
            "Repair rejected by validation agent."
        )

        return {
            "success": False,
            "test": test_name,
            "file": file_path,
            "function": function_name,
            "stage": "validation",
            "message": validation["reason"]
        }

    # --------------------------------------------------
    # Apply repair
    # --------------------------------------------------

    print(
        "\n---------- APPLYING REPAIR ----------"
    )

    application = apply_repair(
        file_path=file_path,
        function_name=function_name,
        old_code=repair["old_code"],
        new_code=repair["new_code"]
    )

    print(
        application
    )

    # --------------------------------------------------
    # Reject failed application
    # --------------------------------------------------

    if not application["success"]:

        return {
            "success": False,
            "test": test_name,
            "file": file_path,
            "function": function_name,
            "stage": "application",
            "message": application["message"]
        }

    # --------------------------------------------------
    # Do NOT run pytest yet.
    #
    # Other diagnosed failures may still exist.
    # --------------------------------------------------

    print(
        f"\nRepair for {test_name} applied successfully."
    )

    print(
        "Waiting for remaining diagnosed repairs "
        "before running the full test suite."
    )

    return {
        "success": True,
        "test": test_name,
        "file": file_path,
        "function": function_name,
        "stage": "applied",
        "message": "Repair validated and applied.",
        "backup": application["backup"],
        "old_code": repair["old_code"],
        "new_code": repair["new_code"]
    }


# --------------------------------------------------
# Rollback all applied repairs
# --------------------------------------------------

def rollback_all_repairs(
    repair_results: list
) -> bool:
    """
    Roll back all successfully applied repairs.

    Repairs are rolled back in reverse order.
    """

    print(
        "\n========== ROLLING BACK ALL REPAIRS =========="
    )

    rollback_success = True

    for result in reversed(
        repair_results
    ):

        if not result.get("success"):
            continue

        file_path = result["file"]

        backup_path = result.get(
            "backup"
        )

        if not backup_path:
            continue

        success = rollback_repair(
            file_path,
            backup_path
        )

        if not success:
            rollback_success = False

    return rollback_success


# --------------------------------------------------
# Autonomous multi-repair workflow
# --------------------------------------------------

async def run_autonomous_repair(
    run_id: int | None = None
) -> dict:
    """
    Execute the complete autonomous repair workflow.

    Supports multiple diagnoses from one CI run.
    """

    print(
        "\n=========================================="
    )

    print(
        "AUTONOMOUS CI/CD REPAIR SYSTEM"
    )

    print(
        "=========================================="
    )

    # --------------------------------------------------
    # STEP 1
    # Diagnose CI run
    # --------------------------------------------------

    print(
        "\n========== STEP 1: CI DIAGNOSIS =========="
    )

    diagnosis_result = await diagnose_run(
        run_id
    )

    diagnosis_data = diagnosis_result[
        "diagnosis"
    ]

    diagnoses = diagnosis_data.get(
        "diagnoses",
        []
    )

    if not diagnoses:

        raise ValueError(
            "No diagnoses were returned by the diagnosis agent."
        )

    print(
        f"\nTotal diagnoses received: "
        f"{len(diagnoses)}"
    )

    # --------------------------------------------------
    # STEP 2
    # Create isolated repair branch
    # --------------------------------------------------

    print(
        "\n========== STEP 2: CREATE REPAIR BRANCH =========="
    )

    repair_run_id = diagnosis_result["run_id"]

    repair_branch = create_repair_branch(
        repair_run_id
    )

    print(
        f"Repair branch created: {repair_branch}"
    )

    # --------------------------------------------------
    # Retrieve implementation source
    # --------------------------------------------------

    all_implementation_source = (
        diagnosis_result.get(
            "implementation_source",
            {}
        )
    )

    # --------------------------------------------------
    # Build test -> implementation source mapping
    # --------------------------------------------------

    failure_contexts = diagnosis_result.get(
        "failure_contexts",
        []
    )

    diagnosis_sources = {}

    for failure_context in failure_contexts:

        test_name = failure_context[
            "test"
        ]

        implementation_targets = (
            failure_context.get(
                "implementation_targets",
                []
            )
        )

        sources = []

        for target in implementation_targets:

            target_file = target["file"]

            source = all_implementation_source.get(
                target_file,
                ""
            )

            if source and source not in sources:

                sources.append(
                    source
                )

        diagnosis_sources[test_name] = (
            "\n\n".join(sources)
        )

    # --------------------------------------------------
    # STEP 3
    # Apply every diagnosis
    # --------------------------------------------------

    print(
        "\n========== STEP 3: MULTI-REPAIR =========="
    )

    repair_results = []

    for index, diagnosis in enumerate(
        diagnoses,
        start=1
    ):

        print(
            f"\n\n========== REPAIR {index} "
            f"OF {len(diagnoses)} =========="
        )

        test_name = diagnosis.get(
            "test",
            ""
        )

        implementation_source = (
            diagnosis_sources.get(
                test_name,
                ""
            )
        )

        try:

            result = process_diagnosis(
                diagnosis,
                implementation_source
            )

            repair_results.append(
                result
            )

            # ------------------------------------------
            # Stop if repair failed
            # ------------------------------------------

            if not result["success"]:

                print(
                    f"\nRepair {index} failed."
                )

                print(
                    "Stopping additional repairs."
                )

                break

        except Exception as error:

            print(
                f"\nRepair {index} crashed:"
            )

            print(
                error
            )

            repair_results.append(
                {
                    "success": False,
                    "test": diagnosis.get(
                        "test",
                        "unknown"
                    ),
                    "file": diagnosis.get(
                        "file",
                        "unknown"
                    ),
                    "function": diagnosis.get(
                        "function",
                        "unknown"
                    ),
                    "stage": "exception",
                    "message": str(error)
                }
            )

            break

    # --------------------------------------------------
    # STEP 4
    # Check whether all repairs were applied
    # --------------------------------------------------

    successful_repairs = sum(
        1
        for result in repair_results
        if result["success"]
    )

    total_diagnoses = len(
        diagnoses
    )

    all_repairs_applied = (
        successful_repairs == total_diagnoses
    )

    if not all_repairs_applied:

        print(
            "\nNot all diagnosed repairs were applied."
        )

        print(
            "Rolling back any repairs that were already applied."
        )

        rollback_success = rollback_all_repairs(
            repair_results
        )

        print(
            f"Rollback complete: "
            f"{rollback_success}"
        )

        return {
            "run_id": diagnosis_result["run_id"],
            "repair_branch": repair_branch,
            "diagnoses": diagnoses,
            "repair_results": repair_results,
            "successful_repairs": successful_repairs,
            "total_diagnoses": total_diagnoses,
            "final_tests_passed": False,
            "final_test_output": "",
            "overall_success": False
        }

    # --------------------------------------------------
    # STEP 5
    # Final full test suite
    # --------------------------------------------------

    print(
        "\n========== STEP 4: FINAL VALIDATION =========="
    )

    print(
        "\nAll diagnosed repairs have been applied."
    )

    print(
        "Now running the complete test suite."
    )

    final_tests_passed, final_test_output = run_tests()

    # --------------------------------------------------
    # STEP 6
    # Final result
    # --------------------------------------------------

    if final_tests_passed:

        print(
            "\n=========================================="
        )

        print(
            "ALL REPAIRS SUCCESSFUL"
        )

        print(
            "=========================================="
        )

        print(
            "All diagnosed failures were repaired."
        )

        print(
            "Full test suite passed."
        )

        # --------------------------------------------------
        # Commit validated repairs
        # --------------------------------------------------

        print(
            "\n---------- COMMITTING REPAIRS ----------"
        )

        commit_message = (
            f"fix: autonomous repair for CI run "
            f"{diagnosis_result['run_id']}"
        )

        commit_output = commit_changes(
            commit_message
        )

        print(
            commit_output
        )

        # --------------------------------------------------
        # Push validated repair branch
        # --------------------------------------------------

        print(
            "\n---------- PUSHING REPAIR BRANCH ----------"
        )

        push_output = push_branch(
            repair_branch
        )

        print(push_output)

        print(
            "\n---------- CREATING PULL REQUEST ----------"
        )

        pr_title = (
            f"fix: autonomous repair for CI run "
            f"{diagnosis_result['run_id']}"
        )

        pr_body = (
            "## Autonomous CI/CD Repair\n\n"
            f"Automatically generated repair for CI run "
            f"`{diagnosis_result['run_id']}`.\n\n"
            "### Validation\n"
            f"- Diagnoses: {len(diagnoses)}\n"
            f"- Successful repairs: {len(successful_repairs)}\n"
            "- Full test suite: **PASSED**\n"
            "- Repairs applied only to validated implementation targets\n"
            "- Changes committed on an isolated repair branch\n\n"
            "Please review the changes before merging."
        )

        pull_request = create_pull_request(
            head_branch=repair_branch,
            base_branch="main",
            title=pr_title,
            body=pr_body
        )

        print(
            f"Pull Request #{pull_request['number']}"
        )

        print(
            f"URL: {pull_request['url']}"
        )

        overall_success = True

    else:

        print(
            "\n=========================================="
        )

        print(
            "FINAL VALIDATION FAILED"
        )

        print(
            "=========================================="
        )

        print(
            "The combined repairs did not produce "
            "a passing test suite."
        )

        rollback_success = rollback_all_repairs(
            repair_results
        )

        print(
            f"Rollback successful: "
            f"{rollback_success}"
        )

        overall_success = False

    # --------------------------------------------------
    # Final summary
    # --------------------------------------------------

    print(
        "\n========== FINAL RESULT =========="
    )

    print(
        f"Repair Branch: "
        f"{repair_branch}"
    )

    print(
        f"Total Diagnoses: "
        f"{total_diagnoses}"
    )

    print(
        f"Successful Repairs: "
        f"{successful_repairs}"
    )

    print(
        f"Final Tests Passed: "
        f"{final_tests_passed}"
    )

    print(
        f"Overall Success: "
        f"{overall_success}"
    )

    return {
        "run_id": diagnosis_result["run_id"],
        "repair_branch": repair_branch,
        "diagnoses": diagnoses,
        "repair_results": repair_results,
        "successful_repairs": successful_repairs,
        "total_diagnoses": total_diagnoses,
        "final_tests_passed": final_tests_passed,
        "final_test_output": final_test_output,
        "overall_success": overall_success
    }


# --------------------------------------------------
# Main
# --------------------------------------------------

async def main():

    result = await run_autonomous_repair()

    print(
        "\n========== AUTONOMOUS REPAIR COMPLETE =========="
    )

    print(
        f"Run ID: {result['run_id']}"
    )

    print(
        f"Repair Branch: "
        f"{result.get('repair_branch', 'N/A')}"
    )

    print(
        f"Diagnoses: "
        f"{result['total_diagnoses']}"
    )

    print(
        f"Successful Repairs: "
        f"{result['successful_repairs']}"
    )

    print(
        f"Final Tests Passed: "
        f"{result['final_tests_passed']}"
    )

    print(
        f"Overall Success: "
        f"{result['overall_success']}"
    )


if __name__ == "__main__":

    anyio.run(main)