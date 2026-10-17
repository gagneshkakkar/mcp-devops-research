
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RUNS_DIR = (
    PROJECT_ROOT
    / "benchmark"
    / "results"
    / "repeated_runs"
)

REQUIRED_TOP_LEVEL_FIELDS = (
    "run_id",
    "approach",
    "started_at_utc",
    "completed_at_utc",
    "model_config",
    "dataset",
    "cases",
)

VALID_STATUSES = {
    "passed",
    "test_failed",
    "error",
    "unsupported",
    "unsupported_syntax_error",
    "rejected",
    "not_started",
}

REQUIRED_CASE_FIELDS = (
    "case_id",
    "status",
    "elapsed_seconds",
    "llm_calls",
    "token_usage",
)


def validate_run(path):
    errors = []

    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        return [f"Could not read valid JSON: {error}"]

    if not isinstance(data, dict):
        return ["Top-level JSON value must be an object."]

    for field in REQUIRED_TOP_LEVEL_FIELDS:
        if field not in data:
            errors.append(f"Missing top-level field: {field}")

    if errors:
        return errors

    for field in (
        "run_id",
        "approach",
        "started_at_utc",
        "completed_at_utc",
    ):
        if not isinstance(data[field], str) or not data[field].strip():
            errors.append(
                f"Field {field!r} must be a non-empty string."
            )

    if not isinstance(data["model_config"], dict):
        errors.append("'model_config' must be an object.")

    if not isinstance(data["dataset"], dict):
        errors.append("'dataset' must be an object.")

    cases = data["cases"]

    if not isinstance(cases, list) or not cases:
        errors.append("'cases' must be a non-empty list.")
        return errors

    seen_case_ids = set()

    for index, case in enumerate(cases):
        prefix = f"cases[{index}]"

        if not isinstance(case, dict):
            errors.append(f"{prefix} must be an object.")
            continue

        for field in REQUIRED_CASE_FIELDS:
            if field not in case:
                errors.append(
                    f"{prefix} is missing required field {field!r}."
                )

        if any(
            field not in case
            for field in REQUIRED_CASE_FIELDS
        ):
            continue

        case_id = case["case_id"]

        if not isinstance(case_id, str) or not case_id.strip():
            errors.append(f"{prefix}.case_id must be a non-empty string.")
        elif case_id in seen_case_ids:
            errors.append(f"Duplicate case ID: {case_id}")
        else:
            seen_case_ids.add(case_id)

        if case["status"] not in VALID_STATUSES:
            errors.append(
                f"{prefix}.status has unsupported value "
                f"{case['status']!r}."
            )

        elapsed = case["elapsed_seconds"]

        if (
            elapsed is not None
            and (
                isinstance(elapsed, bool)
                or not isinstance(elapsed, (int, float))
                or elapsed < 0
            )
        ):
            errors.append(
                f"{prefix}.elapsed_seconds must be a non-negative "
                "number or null."
            )

        llm_calls = case["llm_calls"]

        if (
            isinstance(llm_calls, bool)
            or not isinstance(llm_calls, int)
            or llm_calls < 0
        ):
            errors.append(
                f"{prefix}.llm_calls must be a non-negative integer."
            )

        usage = case["token_usage"]

        if not isinstance(usage, dict):
            errors.append(
                f"{prefix}.token_usage must be an object."
            )
        else:
            for token_field in (
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
            ):
                value = usage.get(token_field)

                if value is not None and (
                    isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 0
                ):
                    errors.append(
                        f"{prefix}.token_usage.{token_field} "
                        "must be a non-negative integer or null."
                    )

        # Component timings are optional, but if supplied they
        # must be non-negative numbers or null.
        for timing_field in (
            "retrieval_seconds",
            "generation_seconds",
            "mcp_seconds",
            "evaluation_seconds",
        ):
            if timing_field not in case:
                continue

            value = case[timing_field]

            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or value < 0
            ):
                errors.append(
                    f"{prefix}.{timing_field} must be a "
                    "non-negative number or null."
                )

    dataset = data["dataset"]

    if isinstance(dataset, dict):
        expected_count = dataset.get("case_count")

        if expected_count is not None:
            if (
                isinstance(expected_count, bool)
                or not isinstance(expected_count, int)
                or expected_count != len(cases)
            ):
                errors.append(
                    "'dataset.case_count' must equal the number "
                    "of case records."
                )

    return errors


def main():
    runs_dir = (
        Path(sys.argv[1]).resolve()
        if len(sys.argv) > 1
        else DEFAULT_RUNS_DIR
    )

    if not runs_dir.is_dir():
        print(f"Runs directory does not exist: {runs_dir}")
        raise SystemExit(1)

    run_files = sorted(runs_dir.glob("*.json"))

    if not run_files:
        print(f"No JSON run files found in: {runs_dir}")
        print("The validator is ready; no runs have been validated yet.")
        return

    failed = 0

    for path in run_files:
        errors = validate_run(path)

        if errors:
            failed += 1
            print(f"\nINVALID: {path.name}")

            for error in errors:
                print(f"  - {error}")
        else:
            print(f"VALID: {path.name}")

    print(
        f"\nValidation summary: "
        f"{len(run_files) - failed}/{len(run_files)} valid"
    )

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
