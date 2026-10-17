
import json
import shutil
from pathlib import Path
from datetime import datetime, timezone


BENCHMARK_ROOT = Path(__file__).parent / "failures"
RESULTS_ROOT = Path(__file__).parent / "results"
WORKSPACES_ROOT = Path(__file__).parent / "workspaces"


def load_cases():
    cases = []

    for case_dir in sorted(BENCHMARK_ROOT.iterdir()):
        metadata_path = case_dir / "metadata.json"

        if not case_dir.is_dir() or not metadata_path.exists():
            continue

        metadata = json.loads(
            metadata_path.read_text(encoding="utf-8")
        )

        broken_path = case_dir / "broken" / "calculator.py"
        expected_path = case_dir / "expected" / "calculator.py"

        if not broken_path.exists():
            raise FileNotFoundError(
                f"Missing broken implementation: {broken_path}"
            )

        if not expected_path.exists():
            raise FileNotFoundError(
                f"Missing expected implementation: {expected_path}"
            )

        cases.append({
            "id": metadata["id"],
            "title": metadata["title"],
            "category": metadata["category"],
            "function": metadata["function"],
            "input": metadata["input"],
            "expected_output": metadata["expected_output"],
            "expected_exception": metadata.get("expected_exception"),
            "broken_file": broken_path,
            "expected_file": expected_path,
        })

    return cases


def main():
    cases = load_cases()

    if not cases:
        raise RuntimeError("No benchmark cases were found.")

    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    WORKSPACES_ROOT.mkdir(parents=True, exist_ok=True)

    experiment_cases = []

    for case in cases:
        case_id = case["id"]
        workspace = WORKSPACES_ROOT / case_id
        workspace.mkdir(parents=True, exist_ok=True)

        # Copy only the broken implementation into the isolated workspace.
        workspace_file = workspace / "calculator.py"
        shutil.copy2(case["broken_file"], workspace_file)

        experiment_cases.append({
            "id": case_id,
            "title": case["title"],
            "category": case["category"],
            "function": case["function"],
            "input": case["input"],
            "expected_output": case["expected_output"],
            "expected_exception": case["expected_exception"],
            "workspace_file": str(workspace_file.resolve()),
            "expected_file": str(case["expected_file"].resolve()),
            "status": "prepared",
            "repair_attempted": False,
            "repair_approved": False,
            "tests_passed": False,
        })

    manifest = {
        "experiment": "autonomous_ci_repair_benchmark",
        "mode": "isolated_workspace",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "total_cases": len(experiment_cases),
        "cases": experiment_cases,
    }

    output_path = RESULTS_ROOT / "experiment_manifest.json"
    output_path.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    print("========== ISOLATED EXPERIMENT SETUP ==========")
    print(f"Mode: {manifest['mode']}")
    print(f"Cases prepared: {len(experiment_cases)}")

    for case in experiment_cases:
        print(f"{case['id']}: {case['status']}")

    print(f"\nManifest saved to: {output_path}")
    print(f"Workspaces created in: {WORKSPACES_ROOT}")


if __name__ == "__main__":
    main()
