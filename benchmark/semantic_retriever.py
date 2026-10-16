
import json
import math
import urllib.request
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_ROOT = PROJECT_ROOT / "benchmark" / "failures"

EMBEDDING_MODEL = "nomic-embed-text"
OLLAMA_EMBED_URL = "http://localhost:11434/api/embed"


def generate_embedding(text):
    """Generate a local embedding using Ollama."""
    payload = json.dumps({
        "model": EMBEDDING_MODEL,
        "input": text,
    }).encode("utf-8")

    request = urllib.request.Request(
        OLLAMA_EMBED_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))

    embeddings = data.get("embeddings", [])

    if not embeddings or not embeddings[0]:
        raise ValueError("Ollama returned an empty embedding.")

    return embeddings[0]


def cosine_similarity(vector_a, vector_b):
    """Calculate cosine similarity between two vectors."""
    if len(vector_a) != len(vector_b):
        raise ValueError("Embedding dimensions do not match.")

    dot_product = sum(
        a * b for a, b in zip(vector_a, vector_b)
    )

    norm_a = math.sqrt(sum(a * a for a in vector_a))
    norm_b = math.sqrt(sum(b * b for b in vector_b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


def load_knowledge_documents():
    """
    Build a knowledge base from benchmark metadata and broken source.

    Expected source files and expected fixes are deliberately excluded
    to prevent answer leakage into retrieval.
    """
    documents = []

    case_directories = sorted(
        path
        for path in BENCHMARK_ROOT.iterdir()
        if path.is_dir()
        and path.name.startswith("F")
        and (path / "metadata.json").is_file()
    )

    for case_dir in case_directories:
        metadata_path = case_dir / "metadata.json"
        broken_path = case_dir / "broken" / "calculator.py"

        metadata = json.loads(
            metadata_path.read_text(encoding="utf-8")
        )

        source = (
            broken_path.read_text(encoding="utf-8")
            if broken_path.exists()
            else ""
        )

        text = "\n".join([
            f"Case ID: {metadata.get('id', case_dir.name)}",
            f"Failure: {metadata.get('title', '')}",
            f"Category: {metadata.get('category', '')}",
            f"Language: {metadata.get('language', 'python')}",
            f"Root cause: {metadata.get('root_cause', '')}",
            f"Function: {metadata.get('function', '')}",
            f"Broken source:\n{source}",
        ])

        documents.append({
            "id": metadata.get("id", case_dir.name),
            "title": metadata.get("title", case_dir.name),
            "category": metadata.get("category", ""),
            "text": text,
        })

    return documents


def retrieve(query, documents, top_k=3, exclude_case_id=None):
    """
    Return the top-k semantically similar documents.

    When exclude_case_id is supplied, that case is removed from the
    candidate corpus before ranking. This supports leave-one-case-out
    evaluation without changing existing callers.
    """
    if top_k < 1:
        raise ValueError("top_k must be at least 1.")

    candidate_documents = [
        document
        for document in documents
        if document["id"] != exclude_case_id
    ]

    if not candidate_documents:
        return []

    query_embedding = generate_embedding(query)
    ranked_documents = []

    for document in candidate_documents:
        embedding = document.get("embedding")

        if embedding is None:
            embedding = generate_embedding(document["text"])
            document["embedding"] = embedding

        score = cosine_similarity(
            query_embedding,
            embedding,
        )

        ranked_documents.append({
            "id": document["id"],
            "title": document["title"],
            "category": document["category"],
            "similarity": round(score, 6),
            "text": document["text"],
        })

    ranked_documents.sort(
        key=lambda item: item["similarity"],
        reverse=True,
    )

    return ranked_documents[:top_k]


def main():
    documents = load_knowledge_documents()

    if not documents:
        raise RuntimeError("No benchmark knowledge documents found.")

    print(f"Knowledge documents: {len(documents)}")
    print(f"Embedding model: {EMBEDDING_MODEL}")

    query = (
        "A Python CI test fails because a function adds two numbers "
        "instead of multiplying them. Find related failure evidence."
    )

    results = retrieve(query, documents, top_k=3)

    print("\nStandard retrieval:")
    for rank, result in enumerate(results, start=1):
        print(
            f"{rank}. {result['id']} - {result['title']} "
            f"(similarity={result['similarity']})"
        )

    excluded_case = "F01"
    loo_results = retrieve(
        query,
        documents,
        top_k=3,
        exclude_case_id=excluded_case,
    )

    print(f"\nLeave-one-case-out retrieval (excluded {excluded_case}):")
    for rank, result in enumerate(loo_results, start=1):
        print(
            f"{rank}. {result['id']} - {result['title']} "
            f"(similarity={result['similarity']})"
        )

    if any(result["id"] == excluded_case for result in loo_results):
        raise RuntimeError(
            f"LOCO check failed: {excluded_case} was retrieved."
        )

    print(f"\nLOCO check passed: {excluded_case} was excluded.")


if __name__ == "__main__":
    main()
