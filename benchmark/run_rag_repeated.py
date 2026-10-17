
import json
import re
import shutil
import statistics
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI

from benchmark.semantic_retriever import (
    load_knowledge_documents,
    retrieve,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_ROOT = PROJECT_ROOT / "benchmark" / "failures"

WORKSPACES_ROOT = (
    PROJECT_ROOT
    / "benchmark"
    / "baseline_workspaces"
    / "rag_repeated"
)

RUNS_ROOT = (
    PROJECT_ROOT
    / "benchmark"
    / "results"
    / "repeated_runs"
)

MODEL_NAME = "qwen2.5-coder:7b"
OLLAMA_BASE_URL = "http://localhost:11434/v1"
EMBEDDING_MODEL = "nomic-embed-text"
TOP_K = 3


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def clean_model_response(content):
    if not content:
        raise ValueError("The model returned an empty response.")

    content = content.strip()
    content = re.sub(
        r"\A```(?:python)?[ \t]*\r?\n",
        "",
        content,
        count=1,
        flags=re.IGNORECASE,
    )
    content = re.sub(
        r"\r?\n```[ \t]*\Z",
        "",
        content,
        count=1,
    )
    content = content.strip()

    if not content:
        raise ValueError("No Python source remained after cleaning.")

    return content + "\n"


def prepare_workspace(case_id):
    broken_path = (
        BENCHMARK_ROOT / case_id / "broken" / "calculator.py"
    )
    workspace_path = (
        WORKSPACES_ROOT / case_id / "calculator.py"
    )

    if not broken_path.is_file():
        raise FileNotFoundError(
            f"Broken source missing: {broken_path}"
        )

    workspace_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(broken_path, workspace_path)
    return workspace_path


def make_repair_prompt(
    case_id, metadata, broken_source, retrieved
):
    evidence = []

    for rank, document in enumerate(retrieved, start=1):
        evidence.append(
            f"Evidence {rank}\n"
            f"Case: {document['id']}\n"
            f"Title: {document['title']}\n"
            f"Category: {document['category']}\n"
            f"Similarity score: {document['similarity']}\n"
            f"Evidence text:\n{document['text']}"
        )

    evidence_text = "\n\n".join(evidence)

    return f"""
You are a Python code repair model.

Repair the supplied broken Python file.

Benchmark case: {case_id}
Failure description: {metadata["title"]}
Failure category: {metadata.get("category", "unknown")}
Target function: {metadata["function"]}
Root cause description: {metadata.get("root_cause", "")}

Retrieved evidence from similar benchmark cases:
{evidence_text}

Rules:
1. Return the complete corrected Python file.
2. Return Python source code only, without Markdown fences.
3. Do not include explanations outside the source code.
4. Preserve unrelated functions and behavior.
5. Do not modify tests or benchmark metadata.
6. Do not hardcode the answer for a single test input.
7. Do not install packages or access the network.
8. Fix the underlying defect.
9. Treat retrieved evidence as reference material, not guaranteed truth.
10. Do not assume an expected test output.

Broken Python file:
--------------------
{broken_source}
--------------------

Return the complete corrected Python file now.
"""


def generate_repair(
    client, case_id, metadata, broken_source, retrieved
):
    prompt = make_repair_prompt(
        case_id, metadata, broken_source, retrieved
    )

    started = time.perf_counter()
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    generation_seconds = time.perf_counter() - started

    source = clean_model_response(
        response.choices[0].message.content
    )

    usage = getattr(response, "usage", None)

    return {
        "source": source,
        "generation_seconds": generation_seconds,
        "token_usage": {
            "prompt_tokens": getattr(
                usage, "prompt_tokens", None
            ),
            "completion_tokens": getattr(
                usage, "completion_tokens", None
            ),
            "total_tokens": getattr(
                usage, "total_tokens", None
            ),
        },
    }


def evaluate_behavior(source_path, metadata):
    source = source_path.read_text(encoding="utf-8")
    compiled = compile(source, str(source_path), "exec")
    namespace = {"__name__": "rag_repeated_benchmark"}
    exec(compiled, namespace)

    function_name = metadata["function"]

    if function_name not in namespace:
        raise ValueError(
            f"Function {function_name!r} was not found."
        )

    actual = namespace[function_name](**metadata["input"])
    expected = metadata["expected_output"]

    return {
        "passed": actual == expected,
        "actual_output": actual,
        "expected_output": expected,
        "actual_exception": None,
        "expected_exception": metadata.get("expected_exception"),
    }


def run_case(client, case_dir, knowledge_documents):
    case_id = case_dir.name
    metadata = read_json(case_dir / "metadata.json")
    started = time.perf_counter()

    record = {
        "case_id": case_id,
        "title": metadata["title"],
        "status": "not_started",
        "elapsed_seconds": None,
        "llm_calls": 0,
        "token_usage": {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
        },
        "retrieval_seconds": None,
        "generation_seconds": None,
        "mcp_seconds": None,
        "evaluation_seconds": None,
        "repair_strategy": "single_llm_plus_semantic_rag",
        "retrieved_documents": [],
        "repair_generated": False,
        "repair_applied": False,
        "tests_passed": False,
        "error": None,
    }

    try:
        workspace_path = prepare_workspace(case_id)
        broken_source = workspace_path.read_text(encoding="utf-8")

        query = "\n".join([
            f"Failure: {metadata['title']}",
            f"Category: {metadata.get('category', '')}",
            f"Root cause: {metadata.get('root_cause', '')}",
            f"Function: {metadata['function']}",
            f"Broken source:\n{broken_source}",
        ])

        retrieval_started = time.perf_counter()
        retrieved = retrieve(
            query,
            knowledge_documents,
            top_k=TOP_K,
        )
        record["retrieval_seconds"] = (
            time.perf_counter() - retrieval_started
        )

        record["retrieved_documents"] = [
            {
                "id": item["id"],
                "title": item["title"],
                "category": item["category"],
                "similarity": item["similarity"],
            }
            for item in retrieved
        ]

        record["llm_calls"] = 1

        generation = generate_repair(
            client,
            case_id,
            metadata,
            broken_source,
            retrieved,
        )

        record["repair_generated"] = True
        record["generation_seconds"] = (
            generation["generation_seconds"]
        )
        record["token_usage"] = generation["token_usage"]

        repaired_source = generation["source"]
        compile(repaired_source, str(workspace_path), "exec")
        workspace_path.write_text(repaired_source, encoding="utf-8")
        record["repair_applied"] = True

        evaluation_started = time.perf_counter()
        behavior = evaluate_behavior(workspace_path, metadata)
        record["evaluation_seconds"] = (
            time.perf_counter() - evaluation_started
        )

        record["behavior"] = behavior
        record["tests_passed"] = behavior["passed"]
        record["status"] = (
            "passed" if behavior["passed"] else "test_failed"
        )

    except Exception as error:
        record["status"] = "error"
        record["error"] = f"{type(error).__name__}: {error}"
        print(f"  Error: {record['error']}")
        traceback.print_exc()

    finally:
        record["elapsed_seconds"] = time.perf_counter() - started

    return record


def main():
    RUNS_ROOT.mkdir(parents=True, exist_ok=True)

    client = OpenAI(
        base_url=OLLAMA_BASE_URL,
        api_key="ollama",
        timeout=180.0,
        max_retries=0,
    )

    case_directories = sorted(
        path
        for path in BENCHMARK_ROOT.iterdir()
        if path.is_dir()
        and path.name.startswith("F")
        and (path / "metadata.json").is_file()
    )

    print("Loading semantic retrieval corpus...")
    corpus_started = time.perf_counter()
    knowledge_documents = load_knowledge_documents()
    corpus_load_seconds = time.perf_counter() - corpus_started

    run_id = str(uuid.uuid4())
    started_at = utc_now()
    results = []

    print("\n========== INSTRUMENTED RAG RUN ==========")
    print(f"Run ID: {run_id}")
    print(f"Model: {MODEL_NAME}")
    print(f"Embedding model: {EMBEDDING_MODEL}")
    print(f"Top K: {TOP_K}")
    print(f"Corpus load time: {corpus_load_seconds:.3f}s")

    for case_dir in case_directories:
        print(f"\nRunning {case_dir.name}...")
        record = run_case(
            client,
            case_dir,
            knowledge_documents,
        )
        results.append(record)

        print(
            f"  Status: {record['status']} | "
            f"Elapsed: {record['elapsed_seconds']:.3f}s | "
            f"Retrieval: {record['retrieval_seconds']} | "
            f"Generation: {record['generation_seconds']}"
        )

    completed_at = utc_now()
    passed = sum(r["status"] == "passed" for r in results)
    total = len(results)

    prompt_tokens = [
        r["token_usage"]["prompt_tokens"]
        for r in results
        if r["token_usage"]["prompt_tokens"] is not None
    ]
    completion_tokens = [
        r["token_usage"]["completion_tokens"]
        for r in results
        if r["token_usage"]["completion_tokens"] is not None
    ]
    total_tokens = [
        r["token_usage"]["total_tokens"]
        for r in results
        if r["token_usage"]["total_tokens"] is not None
    ]

    status_counts = {}
    for record in results:
        status = record["status"]
        status_counts[status] = status_counts.get(status, 0) + 1

    output = {
        "run_id": run_id,
        "approach": "llm_rag",
        "started_at_utc": started_at,
        "completed_at_utc": completed_at,
        "model_config": {
            "provider": "Ollama OpenAI-compatible API",
            "model": MODEL_NAME,
            "endpoint": OLLAMA_BASE_URL,
            "temperature": 0,
            "max_retries": 0,
            "embedding_model": EMBEDDING_MODEL,
            "retrieval_method": "cosine_similarity",
            "top_k": TOP_K,
            "llm_calls": sum(r["llm_calls"] for r in results),
        },
        "dataset": {
            "name": "custom_10_case_ci_failure_benchmark",
            "case_count": total,
            "case_ids": [r["case_id"] for r in results],
        },
        "cases": results,
        "summary": {
            "passed": passed,
            "total_cases": total,
            "pass_rate_percent": round(passed / total * 100, 2)
            if total else 0.0,
            "status_counts": status_counts,
            "corpus_load_seconds": round(corpus_load_seconds, 6),
            "total_elapsed_seconds": round(
                sum(r["elapsed_seconds"] or 0 for r in results), 6
            ),
            "total_retrieval_seconds": round(
                sum(r["retrieval_seconds"] or 0 for r in results), 6
            ),
            "total_generation_seconds": round(
                sum(r["generation_seconds"] or 0 for r in results), 6
            ),
            "token_usage": {
                "prompt_tokens": (
                    sum(prompt_tokens) if len(prompt_tokens) == total
                    else None
                ),
                "completion_tokens": (
                    sum(completion_tokens)
                    if len(completion_tokens) == total else None
                ),
                "total_tokens": (
                    sum(total_tokens) if len(total_tokens) == total
                    else None
                ),
                "cases_with_reported_usage": len(total_tokens),
            },
        },
        "limitations": [
            "Uses a custom 10-case benchmark.",
            "One repair-generation call per case; no retries or fallbacks.",
            "Expected implementations and expected fixes are excluded from retrieval evidence.",
            "Retrieval time includes embedding work performed by the retriever.",
            "Corpus loading time is reported separately from per-case retrieval time.",
            "Local model warm-up, caching, and system load can affect latency.",
            "Generated Python is evaluated only against trusted benchmark cases.",
        ],
    }

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = RUNS_ROOT / (
        f"llm_rag_{timestamp}_{run_id[:8]}.json"
    )

    if output_path.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing run: {output_path}"
        )

    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")

    print("\n========== INSTRUMENTED RAG SUMMARY ==========")
    print(f"Cases: {total}")
    print(f"Passed: {passed}")
    print(f"Pass rate: {output['summary']['pass_rate_percent']}%")
    print(
        "Retrieval seconds: "
        f"{output['summary']['total_retrieval_seconds']}"
    )
    print(
        "Generation seconds: "
        f"{output['summary']['total_generation_seconds']}"
    )
    print(f"Token usage: {output['summary']['token_usage']}")
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()
