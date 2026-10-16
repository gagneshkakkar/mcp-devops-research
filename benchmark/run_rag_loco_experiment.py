
import json
import re
import shutil
import traceback
from pathlib import Path

from openai import OpenAI

from benchmark.semantic_retriever import (
    load_knowledge_documents,
    retrieve,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_ROOT = PROJECT_ROOT / "benchmark" / "failures"

WORKSPACES_ROOT = (
    PROJECT_ROOT / "benchmark" / "baseline_workspaces" / "rag_loco"
)

RESULTS_PATH = (
    PROJECT_ROOT / "benchmark" / "results" / "rag_loco_results.json"
)

MODEL_NAME = "qwen2.5-coder:7b"
OLLAMA_BASE_URL = "http://localhost:11434/v1"
TOP_K = 3

client = OpenAI(
    base_url=OLLAMA_BASE_URL,
    api_key="ollama",
    timeout=180.0,
    max_retries=0,
)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def prepare_workspace(case_id):
    broken_path = (
        BENCHMARK_ROOT / case_id / "broken" / "calculator.py"
    )
    workspace_path = WORKSPACES_ROOT / case_id / "calculator.py"

    if not broken_path.is_file():
        raise FileNotFoundError(
            f"Broken source missing: {broken_path}"
        )

    workspace_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(broken_path, workspace_path)

    return workspace_path


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

    if not content.strip():
        raise ValueError(
            "No Python source remained after cleaning."
        )

    return content.strip() + "\n"


def make_repair_prompt(
    case_id,
    metadata,
    broken_source,
    retrieved,
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

Retrieved evidence from other benchmark cases:
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
11. The retrieved evidence must not be treated as the target case's own source.

Broken Python file:
--------------------
{broken_source}
--------------------

Return the complete corrected Python file now.
"""


def generate_repair(
    case_id,
    metadata,
    broken_source,
    retrieved,
):
    prompt = make_repair_prompt(
        case_id,
        metadata,
        broken_source,
        retrieved,
    )

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )

    return clean_model_response(
        response.choices[0].message.content
    )


def evaluate_behavior(source_path, metadata):
    source = source_path.read_text(encoding="utf-8")

    compiled = compile(source, str(source_path), "exec")

    namespace = {"__name__": "rag_loco_benchmark"}
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


def main():
    case_directories = sorted(
        path
        for path in BENCHMARK_ROOT.iterdir()
        if path.is_dir()
        and path.name.startswith("F")
        and (path / "metadata.json").is_file()
    )

    knowledge_documents = load_knowledge_documents()

    if not knowledge_documents:
        raise RuntimeError(
            "No benchmark knowledge documents found."
        )

    results = {
        "experiment": "single_llm_plus_leave_one_case_out_semantic_rag",
        "model": MODEL_NAME,
        "embedding_model": "nomic-embed-text",
        "retrieval_method": "cosine_similarity_leave_one_case_out",
        "top_k": TOP_K,
        "mode": "single_model_one_attempt_with_loco_retrieval",
        "total_cases": len(case_directories),
        "retrieval_policy": (
            "The current test case is excluded from retrieval candidates."
        ),
        "cases": [],
        "notes": [
            "Uses the same local Qwen model and embedding model as the RAG pilot.",
            "Excludes each target case from its retrieval candidates.",
            "Uses metadata and broken source from other benchmark cases.",
            "Expected implementations and expected fixes are excluded "
            "from retrieval documents.",
            "One repair-generation call is made per case.",
            "No retries, multi-agent orchestrator, or repair fallback is used.",
            "Each case is evaluated in a separate workspace.",
            "This experiment writes to rag_loco_results.json and does not "
            "overwrite the original RAG results.",
            "The evaluator executes generated Python source. Only use "
            "trusted benchmark cases.",
        ],
    }

    for case_dir in case_directories:
        case_id = case_dir.name
        metadata = read_json(case_dir / "metadata.json")

        record = {
            "id": case_id,
            "title": metadata["title"],
            "status": "not_started",
            "repair_strategy": "single_llm_plus_leave_one_case_out_rag",
            "excluded_case_id": case_id,
            "llm_calls": 0,
            "retrieved_documents": [],
            "repair_generated": False,
            "repair_applied": False,
            "tests_passed": False,
            "error": None,
        }

        print(
            f"\n========== {case_id}: {metadata['title']} =========="
        )

        try:
            workspace_path = prepare_workspace(case_id)
            broken_source = workspace_path.read_text(
                encoding="utf-8"
            )

            query = "\n".join([
                f"Failure: {metadata['title']}",
                f"Category: {metadata.get('category', '')}",
                f"Root cause: {metadata.get('root_cause', '')}",
                f"Function: {metadata['function']}",
                f"Broken source:\n{broken_source}",
            ])

            retrieved = retrieve(
                query,
                knowledge_documents,
                top_k=TOP_K,
                exclude_case_id=case_id,
            )

            # Explicitly enforce and verify the LOCO requirement.
            if any(
                item["id"] == case_id
                for item in retrieved
            ):
                raise RuntimeError(
                    f"LOCO violation: {case_id} appeared in retrieval."
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

            print(f"Excluded target case: {case_id}")
            print("Retrieved evidence:")

            for item in retrieved:
                print(
                    f"  {item['id']} - {item['title']} "
                    f"(similarity={item['similarity']})"
                )

            record["llm_calls"] = 1

            repaired_source = generate_repair(
                case_id,
                metadata,
                broken_source,
                retrieved,
            )

            record["repair_generated"] = True

            compile(repaired_source, str(workspace_path), "exec")

            workspace_path.write_text(
                repaired_source,
                encoding="utf-8",
            )
            record["repair_applied"] = True

            behavior = evaluate_behavior(
                workspace_path,
                metadata,
            )

            record["behavior"] = behavior
            record["tests_passed"] = behavior["passed"]
            record["status"] = (
                "passed" if behavior["passed"] else "test_failed"
            )

            print("Outcome:", record["status"])

        except Exception as error:
            record["status"] = "error"
            record["error"] = (
                f"{type(error).__name__}: {error}"
            )
            print("Outcome: error")
            print("Details:", record["error"])
            traceback.print_exc()

        results["cases"].append(record)
        write_json(RESULTS_PATH, results)

    summary = {}

    for record in results["cases"]:
        summary[record["status"]] = (
            summary.get(record["status"], 0) + 1
        )

    passed = summary.get("passed", 0)
    total = len(results["cases"])

    results["summary"] = summary
    results["passed_cases"] = passed
    results["observed_pass_rate_percent"] = (
        round(passed / total * 100, 2) if total else 0
    )

    write_json(RESULTS_PATH, results)

    print("\n========== LOCO RAG EXPERIMENT SUMMARY ==========")
    print(f"Cases recorded: {total}")

    for status, count in sorted(summary.items()):
        print(f"{status}: {count}")

    print(
        "Observed pass rate: "
        f"{results['observed_pass_rate_percent']:.1f}%"
    )
    print(f"Results saved to: {RESULTS_PATH}")


if __name__ == "__main__":
    main()
