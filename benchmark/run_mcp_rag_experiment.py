
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from openai import OpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from benchmark.semantic_retriever import load_knowledge_documents, retrieve


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = PROJECT_ROOT / "benchmark" / "failures"
WORKSPACE_ROOT = PROJECT_ROOT / "benchmark" / "baseline_workspaces" / "mcp_rag"
RESULTS_PATH = PROJECT_ROOT / "benchmark" / "results" / "mcp_rag_results.json"

MODEL_NAME = "qwen2.5-coder:7b"
OLLAMA_BASE_URL = "http://localhost:11434/v1"
OLLAMA_API_KEY = "ollama"
EMBEDDING_MODEL_NAME = "nomic-embed-text"

EXPERIMENT_NAME = "single_llm_plus_semantic_rag_plus_mcp"


def read_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def extract_text(result):
    if getattr(result, "isError", False):
        raise RuntimeError("MCP tool returned an error.")

    parts = [
        item.text
        for item in result.content
        if getattr(item, "type", None) == "text"
    ]

    if not parts:
        raise RuntimeError("MCP tool returned no text evidence.")

    return "\n".join(parts)


async def call_mcp_tool(case_id):
    """Launch the isolated MCP server and call its tool over stdio."""
    server_script = PROJECT_ROOT / "benchmark" / "mcp_evidence_server.py"

    params = StdioServerParameters(
        command=sys.executable,
        args=[str(server_script)],
        cwd=str(PROJECT_ROOT),
        env=os.environ.copy(),
    )

    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools_result = await session.list_tools()
            available = {tool.name for tool in tools_result.tools}

            if "get_case_evidence" not in available:
                raise RuntimeError(
                    "MCP server did not advertise get_case_evidence."
                )

            result = await session.call_tool(
                "get_case_evidence",
                {"case_id": case_id},
            )

            payload = json.loads(extract_text(result))

            if payload.get("error"):
                raise RuntimeError(payload["error"])

            return payload


def get_llm_client():
    return OpenAI(
        base_url=OLLAMA_BASE_URL,
        api_key=OLLAMA_API_KEY,
        timeout=180.0,
    )


def generate_repair(client, case_id, mcp_evidence, retrieved_docs):
    metadata = mcp_evidence["metadata"]
    broken_source = mcp_evidence["broken_source"]

    evidence_sections = []
    for index, doc in enumerate(retrieved_docs, start=1):
        evidence_sections.append(
            f"Retrieved evidence {index}:\n"
            f"{json.dumps(doc, ensure_ascii=False, default=str)}"
        )

    retrieved_context = "\n\n".join(evidence_sections)

    prompt = f"""
Repair this Python program in an isolated benchmark.

Target case: {case_id}
Title: {metadata.get("title", "")}
Category: {metadata.get("category", "")}
Target function: {metadata.get("function", "")}
Reported root cause: {metadata.get("root_cause", "")}
Test input: {json.dumps(metadata.get("input", {}))}

Broken source:
```python
{broken_source}
```

Related evidence retrieved through semantic search:
{retrieved_context}

Requirements:
- Return the complete corrected Python source file, not a diff.
- Preserve unrelated functions and behavior.
- Fix the target defect without introducing unrelated dependencies.
- Do not use markdown fences or explanatory text.
- Treat retrieved examples as evidence, not as identical target cases.
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a careful Python repair assistant. "
                    "Return only complete Python source code."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )

    content = (response.choices[0].message.content or "").strip()

    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    if not content:
        raise RuntimeError("The model returned empty source.")

    return content


def evaluate_repair(source_path, metadata):
    """Syntax-check and execute the target function in a subprocess."""
    import subprocess

    try:
        compile_result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import ast, pathlib, sys; "
                    "ast.parse(pathlib.Path(sys.argv[1]).read_text("
                    "encoding='utf-8'))"
                ),
                str(source_path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if compile_result.returncode != 0:
            return {
                "status": "error",
                "reason": "syntax_error",
                "details": compile_result.stderr[-2000:],
            }

        test_script = r'''
import importlib.util
import json
import sys

path, function_name, input_json = sys.argv[1:4]
spec = importlib.util.spec_from_file_location("benchmark_target", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

function = getattr(module, function_name)
kwargs = json.loads(input_json)
result = function(**kwargs)
print(json.dumps({"output": result}))
'''

        test_result = subprocess.run(
            [
                sys.executable,
                "-c",
                test_script,
                str(source_path),
                metadata["function"],
                json.dumps(metadata.get("input", {})),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if test_result.returncode != 0:
            return {
                "status": "error",
                "reason": "runtime_error",
                "details": test_result.stderr[-2000:],
            }

        result_json = json.loads(
            test_result.stdout.strip().splitlines()[-1]
        )
        actual = result_json["output"]
        expected = metadata["expected_output"]

        if actual == expected:
            return {
                "status": "passed",
                "actual": actual,
                "expected": expected,
            }

        return {
            "status": "test_failed",
            "actual": actual,
            "expected": expected,
        }

    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "reason": "timeout",
            "details": "Evaluation exceeded the time limit.",
        }
    except Exception as error:
        return {
            "status": "error",
            "reason": "evaluation_error",
            "details": str(error),
        }


def write_results(records):
    passed = sum(item["status"] == "passed" for item in records)
    total = len(records)

    payload = {
        "experiment": EXPERIMENT_NAME,
        "model": MODEL_NAME,
        "embedding_model": EMBEDDING_MODEL_NAME,
        "mcp_server": "benchmark/mcp_evidence_server.py",
        "mcp_tool": "get_case_evidence",
        "cases_recorded": total,
        "passed": passed,
        "pass_rate_percent": round(100 * passed / total, 2) if total else 0,
        "results": records,
    }

    RESULTS_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def print_summary(records):
    counts = {}
    for record in records:
        counts[record["status"]] = counts.get(record["status"], 0) + 1

    passed = counts.get("passed", 0)
    total = len(records)
    rate = (100 * passed / total) if total else 0

    print("\n=== A3 MCP + RAG Experiment Summary ===")
    print(f"Cases recorded: {total}")
    print(f"Passed: {passed}")
    print(f"Pass rate: {rate:.1f}%")
    print(f"Statuses: {counts}")
    print(f"Results saved to: {RESULTS_PATH}")


async def run_experiment():
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)

    documents = load_knowledge_documents()
    client = get_llm_client()

    cases = sorted(
        path for path in BENCHMARK_ROOT.iterdir()
        if path.is_dir()
        and path.name.startswith("F")
        and (path / "metadata.json").exists()
    )

    records = []

    for case_dir in cases:
        case_id = case_dir.name
        print(f"\n[{case_id}] Starting MCP + RAG experiment")

        record = {
            "case_id": case_id,
            "experiment": EXPERIMENT_NAME,
            "model": MODEL_NAME,
            "embedding_model": EMBEDDING_MODEL_NAME,
            "mcp_tool_called": False,
            "retrieved_case_ids": [],
            "status": "error",
        }

        try:
            metadata = read_json(case_dir / "metadata.json")
            mcp_evidence = await call_mcp_tool(case_id)

            record["mcp_tool_called"] = True
            record["mcp_tool"] = "get_case_evidence"

            query = (
                f"{metadata.get('title', '')} "
                f"{metadata.get('category', '')} "
                f"{metadata.get('root_cause', '')} "
                f"{metadata.get('function', '')}"
            )
            retrieved_docs = retrieve(query, documents, top_k=3)

            record["retrieved_case_ids"] = [
                str(doc.get("id", doc.get("case_id", "unknown")))
                for doc in retrieved_docs
            ]

            workspace = WORKSPACE_ROOT / case_id
            workspace.mkdir(parents=True, exist_ok=True)
            target_path = workspace / "calculator.py"

            start_time = time.time()
            repaired_source = generate_repair(
                client,
                case_id,
                mcp_evidence,
                retrieved_docs,
            )
            record["generation_seconds"] = round(
                time.time() - start_time, 3
            )

            target_path.write_text(repaired_source, encoding="utf-8")

            evaluation = evaluate_repair(target_path, metadata)
            record["evaluation"] = evaluation
            record["status"] = evaluation["status"]

        except Exception as error:
            record["status"] = "error"
            record["error"] = f"{type(error).__name__}: {error}"

        records.append(record)
        print(f"[{case_id}] Result: {record['status']}")
        write_results(records)

    print_summary(records)


if __name__ == "__main__":
    asyncio.run(run_experiment())
