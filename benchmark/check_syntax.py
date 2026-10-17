
import json
from pathlib import Path

root = Path(__file__).parent / "failures"

for metadata_path in sorted(root.glob("F*/metadata.json")):
    metadata = json.loads(
        metadata_path.read_text(encoding="utf-8")
    )

    source_path = (
        metadata_path.parent / "broken" / "calculator.py"
    )
    source = source_path.read_text(encoding="utf-8")

    try:
        compile(source, str(source_path), "exec")
        syntax = "VALID"
    except SyntaxError:
        syntax = "SYNTAX_ERROR"

    print(
        metadata["id"],
        "|",
        metadata["category"],
        "|",
        syntax,
    )
