
import json
from pathlib import Path

from mcp.server import MCPServer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = PROJECT_ROOT / "benchmark" / "failures"

mcp = MCPServer(
    name="Benchmark Evidence MCP Server",
    instructions=(
        "Provide read-only evidence for controlled CI/CD repair experiments. "
        "Return only the requested case's public metadata and broken source. "
        "Never expose expected fixes or evaluation answers."
    ),
)


@mcp.tool()
def get_case_evidence(case_id: str) -> str:
    """Read public metadata and broken source for one benchmark case."""

    # Accept only IDs such as F01 through F10.
    if (
        len(case_id) != 3
        or not case_id.startswith("F")
        or not case_id[1:].isdigit()
        or not 1 <= int(case_id[1:]) <= 10
    ):
        return json.dumps({"error": "Invalid benchmark case ID."})

    case_dir = BENCHMARK_ROOT / case_id
    metadata_path = case_dir / "metadata.json"
    source_path = case_dir / "broken" / "calculator.py"

    try:
        with metadata_path.open("r", encoding="utf-8") as file:
            metadata = json.load(file)

        with source_path.open("r", encoding="utf-8") as file:
            broken_source = file.read()

        # Explicit allowlist prevents expected answers from leaking
        # into the model's prompt through the MCP tool.
        public_fields = (
            "id",
            "title",
            "category",
            "language",
            "function",
            "root_cause",
            "difficulty",
            "input",
        )

        public_metadata = {
            key: metadata[key]
            for key in public_fields
            if key in metadata
        }

        return json.dumps(
            {
                "case_id": case_id,
                "metadata": public_metadata,
                "broken_source": broken_source,
            },
            indent=2,
        )

    except FileNotFoundError:
        return json.dumps(
            {"error": f"Benchmark files are missing for {case_id}."}
        )
    except (OSError, json.JSONDecodeError) as error:
        return json.dumps(
            {"error": f"Could not read benchmark evidence: {error}"}
        )


if __name__ == "__main__":
    mcp.run(transport="stdio")
