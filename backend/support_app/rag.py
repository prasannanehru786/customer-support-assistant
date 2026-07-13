from __future__ import annotations

import json
import hashlib
import os
import re
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.support_app.config import (
    EMBEDDING_MODEL,
    KNOWLEDGE_DIR,
    QDRANT_COLLECTION,
    QDRANT_URL,
    RAG_INDEX_STATE_PATH,
    ensure_runtime_dirs,
)
from backend.support_app.costs import aggregate_costs, estimate_cost
from backend.support_app.models import KnowledgeChunk, Source, UsageCost
from backend.support_app.openai_clients import make_openai_client
from backend.support_app.utils import sha256_text


def retrieve_local_knowledge(query: str) -> tuple[str, list[Source], bool]:
    """Lightweight local fallback before Qdrant: keyword search over ./knowledge/*.txt."""
    query_terms = {term.lower() for term in re.findall(r"[A-Za-z0-9_]+", query) if len(term) > 2}
    if not query_terms:
        return "", [], False

    candidates: list[tuple[int, Path, str]] = []
    for path in KNOWLEDGE_DIR.glob("**/*.txt"):
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        score = sum(1 for term in query_terms if term in content.lower())
        if score:
            candidates.append((score, path, content[:2500]))

    candidates.sort(key=lambda item: item[0], reverse=True)
    chosen = candidates[:3]
    sources = [
        Source(
            title=path.name,
            url=f"knowledge/{path.relative_to(KNOWLEDGE_DIR)}",
            snippet=snippet[:300],
            rank=rank,
            source_type="local_knowledge",
        )
        for rank, (_score, path, snippet) in enumerate(chosen, start=1)
    ]
    context = "\n\n".join(f"Source: {path.name}\n{snippet}" for _score, path, snippet in chosen)
    return context, sources, bool(chosen)


def tokenize_for_rag(text: str) -> list[str]:
    return [term.lower() for term in re.findall(r"[A-Za-z0-9_]+", text) if len(term) > 2]


def chunk_text(text: str) -> list[str]:
    max_chars = int(os.getenv("RAG_CHUNK_CHARS", "1200"))
    overlap = min(int(os.getenv("RAG_CHUNK_OVERLAP_CHARS", "160")), max_chars // 2)
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(start + max_chars, len(cleaned))
        chunks.append(cleaned[start:end])
        if end == len(cleaned):
            break
        start = max(end - overlap, start + 1)
    return chunks


def load_knowledge_chunks() -> list[KnowledgeChunk]:
    chunks: list[KnowledgeChunk] = []
    max_chunks = int(os.getenv("MAX_RAG_CHUNKS_TO_INDEX", "256"))
    for path in sorted(KNOWLEDGE_DIR.glob("**/*.txt")):
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        relative_path = str(path.relative_to(KNOWLEDGE_DIR))
        for chunk_id, chunk in enumerate(chunk_text(content)):
            chunks.append(KnowledgeChunk(path=relative_path, chunk_id=chunk_id, text=chunk))
            if len(chunks) >= max_chunks:
                return chunks
    return chunks


def knowledge_fingerprint(chunks: list[KnowledgeChunk]) -> str:
    hasher = hashlib.sha256()
    for chunk in chunks:
        hasher.update(chunk.path.encode("utf-8"))
        hasher.update(str(chunk.chunk_id).encode("utf-8"))
        hasher.update(chunk.text.encode("utf-8"))
    return hasher.hexdigest()


def point_id_for_chunk(chunk: KnowledgeChunk) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{chunk.path}:{chunk.chunk_id}:{sha256_text(chunk.text)}"))


def embed_texts(texts: list[str]) -> tuple[list[list[float]], UsageCost]:
    if not texts or not os.getenv("OPENAI_API_KEY"):
        return [], UsageCost()
    client = make_openai_client()
    if client is None:
        return [], UsageCost()
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    vectors = [list(item.embedding) for item in response.data]
    usage = getattr(response, "usage", None)
    embedding_tokens = int(getattr(usage, "total_tokens", 0) or 0)
    return vectors, estimate_cost(0, 0, 0, embedding_tokens=embedding_tokens)


def load_rag_index_state() -> dict[str, Any]:
    if not RAG_INDEX_STATE_PATH.exists():
        return {}
    try:
        return json.loads(RAG_INDEX_STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_rag_index_state(state: dict[str, Any]) -> None:
    ensure_runtime_dirs()
    RAG_INDEX_STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def ensure_qdrant_index(chunks: list[KnowledgeChunk]) -> tuple[Any | None, UsageCost]:
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, PointStruct, VectorParams
    except ImportError:
        return None, UsageCost()

    if not chunks:
        return None, UsageCost()

    client = QdrantClient(url=QDRANT_URL, timeout=float(os.getenv("QDRANT_TIMEOUT_SECONDS", "8")))
    fingerprint = knowledge_fingerprint(chunks)
    state = load_rag_index_state()
    collection_exists = client.collection_exists(QDRANT_COLLECTION)
    if collection_exists and state.get("fingerprint") == fingerprint:
        return client, UsageCost()

    vectors, cost = embed_texts([chunk.text for chunk in chunks])
    if not vectors:
        return None, cost

    if collection_exists:
        client.delete_collection(collection_name=QDRANT_COLLECTION)
    client.create_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=VectorParams(size=len(vectors[0]), distance=Distance.COSINE),
    )
    points = [
        PointStruct(
            id=point_id_for_chunk(chunk),
            vector=vector,
            payload={
                "path": chunk.path,
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                "title": Path(chunk.path).name,
            },
        )
        for chunk, vector in zip(chunks, vectors)
    ]
    client.upsert(collection_name=QDRANT_COLLECTION, points=points)
    save_rag_index_state(
        {
            "fingerprint": fingerprint,
            "collection": QDRANT_COLLECTION,
            "chunk_count": len(chunks),
            "embedding_model": EMBEDDING_MODEL,
            "indexed_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return client, cost


def retrieve_hybrid_rag(query: str) -> tuple[str, list[Source], bool, UsageCost]:
    if os.getenv("ENABLE_HYBRID_RAG", "true").lower() != "true":
        return "", [], False, UsageCost()

    chunks = load_knowledge_chunks()
    if not chunks:
        return "", [], False, UsageCost()

    try:
        qdrant_client, index_cost = ensure_qdrant_index(chunks)
        query_vectors, query_cost = embed_texts([query])
        if qdrant_client is None or not query_vectors:
            return "", [], False, aggregate_costs(index_cost, query_cost)

        semantic_hits = qdrant_client.search(
            collection_name=QDRANT_COLLECTION,
            query_vector=query_vectors[0],
            limit=int(os.getenv("RAG_SEMANTIC_LIMIT", "8")),
        )
    except Exception:
        return "", [], False, UsageCost()

    chunk_lookup = {f"{chunk.path}:{chunk.chunk_id}": chunk for chunk in chunks}
    semantic_keys: list[str] = []
    for hit in semantic_hits:
        payload = hit.payload or {}
        path = str(payload.get("path", ""))
        chunk_id = payload.get("chunk_id")
        if path and chunk_id is not None:
            semantic_keys.append(f"{path}:{chunk_id}")

    bm25_keys: list[str] = []
    try:
        from rank_bm25 import BM25Okapi

        tokenized_chunks = [tokenize_for_rag(chunk.text) for chunk in chunks]
        bm25 = BM25Okapi(tokenized_chunks)
        bm25_scores = bm25.get_scores(tokenize_for_rag(query))
        ranked = sorted(enumerate(bm25_scores), key=lambda item: item[1], reverse=True)
        bm25_keys = [
            f"{chunks[index].path}:{chunks[index].chunk_id}"
            for index, score in ranked[: int(os.getenv("RAG_BM25_LIMIT", "8"))]
            if score > 0
        ]
    except Exception:
        bm25_keys = []

    fused_scores: dict[str, float] = defaultdict(float)
    for rank, key in enumerate(semantic_keys, start=1):
        fused_scores[key] += 1 / (60 + rank)
    for rank, key in enumerate(bm25_keys, start=1):
        fused_scores[key] += 1 / (60 + rank)

    chosen_keys = [
        key
        for key, _score in sorted(fused_scores.items(), key=lambda item: item[1], reverse=True)
        if key in chunk_lookup
    ][: int(os.getenv("RAG_TOP_K", "3"))]
    chosen_chunks = [chunk_lookup[key] for key in chosen_keys]
    if not chosen_chunks:
        return "", [], False, aggregate_costs(index_cost, query_cost)

    sources = [
        Source(
            title=Path(chunk.path).name,
            url=f"knowledge/{chunk.path}#chunk-{chunk.chunk_id}",
            snippet=chunk.text[:300],
            rank=rank,
            source_type="hybrid_rag",
        )
        for rank, chunk in enumerate(chosen_chunks, start=1)
    ]
    context = "\n\n".join(
        f"Source: {chunk.path} chunk {chunk.chunk_id}\n{chunk.text}" for chunk in chosen_chunks
    )
    return context, sources, True, aggregate_costs(index_cost, query_cost)
