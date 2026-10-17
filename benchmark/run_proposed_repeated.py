
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from benchmark import run_repair_experiment as pipeline


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8",
    )


def main():
    # Each invocation creates a unique run and workspace.
    run_id = str(uuid.uuid4())
    run_started = time.perf_counter()
    started_at_utc = utc_now()

    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    run_root = (
        PROJECT_ROOT
        / "benchmark"
        / "baseline_workspaces"
        / "proposed_repeated"
        / run_id
    )

    workspace_root = run_root / "workspaces"
    manifest_path = run_root / "experiment_manifest.json"

    results_path = (
        PROJECT_ROOT
        / "benchmark"
        / "results"
        / "repeated_runs"
        / f"proposed_{timestamp}_{run_id[:8]}.json"
    )

    run_root.mkdir(parents=True, exist_ok=False)
    workspace_root.mkdir(parents=True, exist_ok=True)

    # Read the existing manifest without modifying it.
    original_manifest_path = (
        PROJECT_ROOT
        / "benchmark"
        / "results"
        / "experiment_manifest.json"
    )

    if not original_manifest_path.is_file():
        raise FileNotFoundError(
            f"Original manifest not found: {original_manifest_path}"
        )

    manifest = json.loads(
        original_manifest_path.read_text(encoding="utf-8")
    )

    # Point every case at this run's private workspace.
    for case in manifest["cases"]:
        case_id = case["id"]

        case["workspace_file"] = str(
            (
                workspace_root
                / case_id
                / "calculator.py"
            ).resolve()
        )

        # Keep expected implementations inside the benchmark dataset.
        expected_file = Path(case["expected_file"]).resolve()
        expected_file.relative_to(
            (PROJECT_ROOT / "benchmark" / "failures").resolve()
        )
        case["expected_file"] = str(expected_file)

    manifest["mode"] = "isolated_repeated_run"
    manifest["created_at"] = started_at_utc
    manifest["run_id"] = run_id

    write_json(manifest_path, manifest)

    # Per-case measurements.
    metrics = {
        case["id"]: {
            "started": None,
            "llm_calls": 0,
            "generation_seconds": 0.0,
            "validation_seconds": 0.0,
            "application_seconds": 0.0,
            "evaluation_seconds": 0.0,
        }
        for case in manifest["cases"]
    }

    current_case = {"id": None}

    # Save original functions so they can be restored after the run.
    original_functions = {
        "prepare_workspace": pipeline.prepare_workspace,
        "generate_repair": pipeline.generate_repair,
        "validate_repair": pipeline.validate_repair,
        "apply_repair": pipeline.apply_repair,
        "evaluate_behavior": pipeline.evaluate_behavior,
        "finish_case": pipeline.finish_case,
    }

    # Point the imported pipeline to isolated paths.
    original_constants = {
        "WORKSPACES_ROOT": pipeline.WORKSPACES_ROOT,
        "MANIFEST_PATH": pipeline.MANIFEST_PATH,
        "RESULTS_PATH": pipeline.RESULTS_PATH,
    }

    pipeline.WORKSPACES_ROOT = workspace_root
    pipeline.MANIFEST_PATH = manifest_path
    pipeline.RESULTS_PATH = results_path

    def measured_prepare_workspace(case_id, workspace_file):
        current_case["id"] = case_id
        metrics[case_id]["started"] = time.perf_counter()

        return original_functions["prepare_workspace"](
            case_id,
            workspace_file,
        )

    def measured_generate_repair(*args, **kwargs):
        case_id = current_case["id"]

        if case_id is not None:
            metrics[case_id]["llm_calls"] += 1

        started = time.perf_counter()

        try:
            return original_functions["generate_repair"](
                *args,
                **kwargs,
            )
        finally:
            if case_id is not None:
                metrics[case_id]["generation_seconds"] += (
                    time.perf_counter() - started
                )

    def measured_validate_repair(*args, **kwargs):
        case_id = current_case["id"]
        started = time.perf_counter()

        try:
            return original_functions["validate_repair"](
                *args,
                **kwargs,
            )
        finally:
            if case_id is not None:
                metrics[case_id]["validation_seconds"] += (
                    time.perf_counter() - started
                )

    def measured_apply_repair(*args, **kwargs):
        case_id = current_case["id"]
        started = time.perf_counter()

        try:
            return original_functions["apply_repair"](
                *args,
                **kwargs,
            )
        finally:
            if case_id is not None:
                metrics[case_id]["application_seconds"] += (
                    time.perf_counter() - started
                )

    def measured_evaluate_behavior(*args, **kwargs):
        case_id = current_case["id"]
        started = time.perf_counter()

        try:
            return original_functions["evaluate_behavior"](
                *args,
                **kwargs,
            )
        finally:
            if case_id is not None:
                metrics[case_id]["evaluation_seconds"] += (
                    time.perf_counter() - started
                )

    def measured_finish_case(results, record):
        case_id = record["id"]
        case_metrics = metrics[case_id]
        case_started = case_metrics["started"]

        record["case_id"] = case_id
        record["llm_calls"] = case_metrics["llm_calls"]

        record["elapsed_seconds"] = (
            round(time.perf_counter() - case_started, 6)
            if case_started is not None
            else None
        )

        record["generation_seconds"] = round(
            case_metrics["generation_seconds"], 6
        )
        record["validation_seconds"] = round(
            case_metrics["validation_seconds"], 6
        )
        record["application_seconds"] = round(
            case_metrics["application_seconds"], 6
        )
        record["evaluation_seconds"] = round(
            case_metrics["evaluation_seconds"], 6
        )

        # The current repair/validator functions do not expose
        # token usage from their underlying LLM responses.
        record["token_usage"] = None

        return original_functions["finish_case"](
            results,
            record,
        )

    pipeline.prepare_workspace = measured_prepare_workspace
    pipeline.generate_repair = measured_generate_repair
    pipeline.validate_repair = measured_validate_repair
    pipeline.apply_repair = measured_apply_repair
    pipeline.evaluate_behavior = measured_evaluate_behavior
    pipeline.finish_case = measured_finish_case

    try:
        print("========== PROPOSED SYSTEM REPEATED RUN ==========")
        print(f"Run ID: {run_id}")
        print(f"Cases: {len(manifest['cases'])}")
        print(f"Workspace: {workspace_root}")
        print(f"Results: {results_path}")
        print("GitHub orchestrator: NOT INVOKED")
        print("Historical results: WILL NOT BE OVERWRITTEN")

        pipeline.main()

    finally:
        # Restore the imported pipeline's original functions and paths.
        for name, function in original_functions.items():
            setattr(pipeline, name, function)

        for name, value in original_constants.items():
            setattr(pipeline, name, value)

    # Add repeatability metadata to this run's unique result file.
    results = json.loads(
        results_path.read_text(encoding="utf-8")
    )

    completed_at_utc = utc_now()
    total_elapsed = round(time.perf_counter() - run_started, 6)

    results.update({
        "run_id": run_id,
        "approach": "proposed_multi_agent_repair",
        "started_at_utc": started_at_utc,
        "completed_at_utc": completed_at_utc,
        "elapsed_seconds": total_elapsed,
        "model_config": {
            "repair_model": "qwen2.5-coder:7b",
            "validator_model": "qwen2.5-coder:7b",
            "endpoint": "http://localhost:11434/v1",
            "max_repair_generation_attempts_per_case": 2,
            "temperature": "agent defaults",
        },
        "dataset": {
            "name": "custom_10_case_ci_failure_benchmark",
            "case_count": len(manifest["cases"]),
            "case_ids": [
                case["id"] for case in manifest["cases"]
            ],
        },
        "measurement_notes": [
            "Each run uses a unique isolated workspace.",
            "Generation, validation, application and evaluation timings "
            "are measured separately where those functions are called.",
            "Per-case elapsed time begins immediately before workspace "
            "preparation; it is not identical to process wall-clock time.",
            "Total elapsed time measures the runner's wall-clock duration.",
            "Token usage is unavailable through the current agent interfaces.",
            "The benchmark executes trusted, locally authored test cases.",
            "This runner does not invoke the GitHub-connected orchestrator.",
        ],
    })

    write_json(results_path, results)

    print("\n========== REPEATED RUN COMPLETE ==========")
    print(f"Run ID: {run_id}")
    print(f"Total cases recorded: {len(results['cases'])}")
    print(f"Elapsed seconds: {total_elapsed}")
    print(f"Results saved: {results_path}")


if __name__ == "__main__":
    main()
