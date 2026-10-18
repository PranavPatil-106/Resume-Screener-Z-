import os
import shutil
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection

from chunker import TextChunk
from database import RESUME_STORAGE_DIR
from embedding_provider import EmbeddingProvider, get_embedding_provider

# Track active clients so we can cleanly stop their systems on Windows before deleting session files
_active_session_clients: dict[str, ClientAPI] = {}


def get_safe_model_tag(model_name: str) -> str:
    """Format an embedding model identifier into a safe tag for collection naming."""
    clean = model_name.split("/")[-1].replace("-", "_").replace(".", "_").replace(":", "_").lower()
    tag = "".join(c if c.isalnum() or c == "_" else "_" for c in clean).strip("_")
    return tag or "default"


def get_session_collection_name(session_id: str, model_name: str) -> str:
    """
    Generate a versioned Chroma collection name unique to both the screening session
    and the specific embedding model.
    Ensures 384-dim (BGE) and 768-dim (Nomic) vectors are never mixed.
    """
    safe_session = session_id.replace("-", "_")
    model_tag = get_safe_model_tag(model_name)
    base_name = f"sess_{safe_session}_{model_tag}"
    # Chroma collection names must be 3-63 characters, start/end with alphanumeric
    if len(base_name) > 63:
        base_name = base_name[:63].rstrip("_")
    return base_name


def get_session_chroma_dir(session_id: str) -> Path:
    """Return the Chroma storage directory nested inside the session's temporary storage."""
    return RESUME_STORAGE_DIR / session_id / "chroma"


def get_session_collection(
    session_id: str,
    model_name: Optional[str] = None,
) -> Collection:
    """
    Get or create the model-versioned ChromaDB collection for a screening session.
    The collection is strictly isolated to the session's temporary directory.
    """
    global _active_session_clients

    if model_name is None:
        provider = get_embedding_provider()
        model_name = getattr(provider, "model_name", "nomic-embed-text")

    chroma_dir = get_session_chroma_dir(session_id)
    chroma_dir.mkdir(parents=True, exist_ok=True)

    client = _active_session_clients.get(session_id)
    if client is None:
        client = chromadb.PersistentClient(path=str(chroma_dir))
        _active_session_clients[session_id] = client

    col_name = get_session_collection_name(session_id, model_name)
    collection = client.get_or_create_collection(
        name=col_name,
        metadata={"hnsw:space": "cosine", "model_name": model_name},
    )
    return collection


def cleanup_old_collections(session_id: str, active_model_name: str) -> None:
    """
    Removes older or legacy model collections for this session once a new index has been built.
    Preserves the collection for active_model_name.
    """
    global _active_session_clients
    chroma_dir = get_session_chroma_dir(session_id)
    if not chroma_dir.exists():
        return

    client = _active_session_clients.get(session_id)
    if client is None:
        try:
            client = chromadb.PersistentClient(path=str(chroma_dir))
            _active_session_clients[session_id] = client
        except Exception:
            return

    active_col_name = get_session_collection_name(session_id, active_model_name)
    try:
        collections = client.list_collections()
        for col in collections:
            c_name = col.name if hasattr(col, "name") else str(col)
            if c_name != active_col_name:
                try:
                    client.delete_collection(name=c_name)
                except Exception:
                    pass
    except Exception:
        pass


def close_session_chroma(session_id: str) -> None:
    """
    Stop the ChromaDB client system and release all file locks on Windows
    so the session directory can be deleted cleanly.
    """
    import gc
    global _active_session_clients
    client = _active_session_clients.pop(session_id, None)
    if client is not None:
        try:
            client._system.stop()
        except Exception:
            pass
        del client
    gc.collect()


def remove_session_storage_dir(session_storage_dir: Path) -> None:
    """
    Safely delete session storage directory on Windows with retries
    to accommodate Windows asynchronous file handle release.
    Removes all model-versioned collections nested in the session directory.
    """
    import gc
    import time
    if not session_storage_dir.exists():
        return

    for _ in range(5):
        try:
            shutil.rmtree(session_storage_dir)
            return
        except OSError:
            gc.collect()
            time.sleep(0.1)

    if session_storage_dir.exists():
        shutil.rmtree(session_storage_dir, ignore_errors=True)


def index_resume_chunks(
    session_id: str,
    resume_id: str,
    source_filename: str,
    chunks: list[TextChunk],
    provider: Optional[EmbeddingProvider] = None,
) -> int:
    """
    Idempotently add chunk embeddings for a specific resume into the session's model-versioned Chroma collection.
    Clears any prior chunks for this resume_id in the target collection to prevent duplicates.
    Returns the number of indexed chunks.
    """
    if provider is None:
        provider = get_embedding_provider()

    model_name = getattr(provider, "model_name", "nomic-embed-text")
    collection = get_session_collection(session_id, model_name=model_name)

    # 1. Idempotency: remove any prior chunks for this resume_id in this collection
    try:
        collection.delete(where={"resume_id": resume_id})
    except Exception:
        pass

    if not chunks:
        return 0

    chunk_ids = [f"{resume_id}_{c['index']}" for c in chunks]
    chunk_texts = [c["text"] for c in chunks]
    chunk_metadatas = [
        {
            "session_id": session_id,
            "resume_id": resume_id,
            "source_filename": source_filename,
            "chunk_index": c["index"],
            "model_name": model_name,
        }
        for c in chunks
    ]

    # Generate embeddings via provider
    chunk_embeddings = provider.embed_documents(chunk_texts)

    collection.add(
        ids=chunk_ids,
        documents=chunk_texts,
        embeddings=chunk_embeddings,
        metadatas=chunk_metadatas,
    )

    return len(chunks)


def delete_resume_from_index(
    session_id: str,
    resume_id: str,
    model_name: Optional[str] = None,
) -> None:
    """Remove chunks belonging to a specific resume from the session's versioned Chroma collection."""
    try:
        chroma_dir = get_session_chroma_dir(session_id)
        if not chroma_dir.exists():
            return
        collection = get_session_collection(session_id, model_name=model_name)
        collection.delete(where={"resume_id": resume_id})
    except Exception:
        pass


def search_session(
    session_id: str,
    query: str,
    top_k: int = 5,
    provider: Optional[EmbeddingProvider] = None,
) -> list[dict]:
    """
    Perform semantic search strictly confined to the requested screening session
    and the current active embedding model collection. Never queries mismatched vector dimensions.
    Returns a list of dicts with chunk_text, source_filename, resume_id, chunk_index, and similarity_distance.
    """
    if provider is None:
        provider = get_embedding_provider()

    chroma_dir = get_session_chroma_dir(session_id)
    if not chroma_dir.exists():
        return []

    model_name = getattr(provider, "model_name", "nomic-embed-text")
    collection = get_session_collection(session_id, model_name=model_name)
    total_chunks = collection.count()
    if total_chunks == 0:
        return []

    actual_k = min(max(1, top_k), total_chunks)

    # Embed query using current provider
    query_vector = provider.embed_query(query)

    query_res = collection.query(
        query_embeddings=[query_vector],
        n_results=actual_k,
        include=["documents", "metadatas", "distances"],
    )

    results: list[dict] = []
    docs = query_res.get("documents", [[]])[0]
    metas = query_res.get("metadatas", [[]])[0]
    distances = query_res.get("distances", [[]])[0]

    for i in range(len(docs)):
        m = metas[i] if i < len(metas) else {}
        d = float(distances[i]) if i < len(distances) else 0.0
        results.append(
            {
                "chunk_text": docs[i],
                "source_filename": str(m.get("source_filename", "")),
                "resume_id": str(m.get("resume_id", "")),
                "chunk_index": int(m.get("chunk_index", 0)),
                "similarity_distance": round(d, 4),
            }
        )

    return results


def batch_search_criteria_for_resume(
    session_id: str,
    resume_id: str,
    query_embeddings: list[list[float]],
    top_k: int = 3,
    provider: Optional[EmbeddingProvider] = None,
) -> list[list[dict]]:
    """
    Search vector chunks belonging to a specific resume_id across multiple criteria embeddings.
    Strictly isolated to the requested screening session and model-versioned collection.
    Returns a list of lists of chunk dicts (one list per criterion embedding).
    """
    if not query_embeddings:
        return []

    if provider is None:
        provider = get_embedding_provider()

    chroma_dir = get_session_chroma_dir(session_id)
    if not chroma_dir.exists():
        return [[] for _ in query_embeddings]

    model_name = getattr(provider, "model_name", "nomic-embed-text")
    collection = get_session_collection(session_id, model_name=model_name)
    total_chunks = collection.count()
    if total_chunks == 0:
        return [[] for _ in query_embeddings]

    actual_k = min(max(1, top_k), total_chunks)

    try:
        query_res = collection.query(
            query_embeddings=query_embeddings,
            n_results=actual_k,
            where={"resume_id": resume_id},
            include=["documents", "metadatas", "distances"],
        )
    except Exception:
        return [[] for _ in query_embeddings]

    all_docs = query_res.get("documents", [])
    all_metas = query_res.get("metadatas", [])
    all_distances = query_res.get("distances", [])

    results_by_criterion: list[list[dict]] = []

    for c_idx in range(len(query_embeddings)):
        crit_results: list[dict] = []
        docs = all_docs[c_idx] if c_idx < len(all_docs) else []
        metas = all_metas[c_idx] if c_idx < len(all_metas) else []
        distances = all_distances[c_idx] if c_idx < len(all_distances) else []

        for i in range(len(docs)):
            m = metas[i] if i < len(metas) else {}
            d = float(distances[i]) if i < len(distances) else 0.0
            crit_results.append(
                {
                    "chunk_text": docs[i],
                    "source_filename": str(m.get("source_filename", "")),
                    "resume_id": str(m.get("resume_id", "")),
                    "chunk_index": int(m.get("chunk_index", 0)),
                    "similarity_distance": round(d, 4),
                }
            )
        results_by_criterion.append(crit_results)

    return results_by_criterion
