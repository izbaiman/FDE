"""
Vector store layer using Chroma with a local sentence-transformers embedding
model (no external embedding API required, keeps the project runnable
offline once the model is cached).

One collection, `documents`, holds chunks from all three unstructured
source types. Metadata (`source_type`, `source_file`) is what lets the
synthesis step cite where each piece of context came from, and would let
you filter (e.g. "only search emails") if a future router decision wanted
to be that specific.
"""
import chromadb
from chromadb.utils import embedding_functions

from app.config import settings

_client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
_embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name=settings.embedding_model
)
_collection = _client.get_or_create_collection(
    name="documents",
    embedding_function=_embedding_fn,
)


def add_chunks(ids: list[str], texts: list[str], metadatas: list[dict]) -> None:
    """Upsert chunks into the vector store. Safe to call repeatedly with the
    same ids - Chroma will overwrite rather than duplicate."""
    _collection.upsert(ids=ids, documents=texts, metadatas=metadatas)


def query(text: str, n_results: int = 5) -> list[dict]:
    """Return the top-k most relevant chunks with their source metadata."""
    result = _collection.query(query_texts=[text], n_results=n_results)
    hits = []
    for doc, meta, dist in zip(
        result["documents"][0], result["metadatas"][0], result["distances"][0]
    ):
        hits.append({"text": doc, "metadata": meta, "distance": dist})
    return hits


def collection_count() -> int:
    return _collection.count()
