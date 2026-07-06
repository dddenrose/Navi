"""Embedding service — text-embedding-004 + Firestore Vector Search."""

from google.cloud import firestore as firestore_module
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector
from vertexai.language_models import TextEmbeddingInput, TextEmbeddingModel

from config import settings
from services.firestore_client import get_db

_embedding_model: TextEmbeddingModel | None = None


def _get_embedding_model() -> TextEmbeddingModel:
    """Return the embedding model singleton."""
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = TextEmbeddingModel.from_pretrained(settings.embedding_model_name)
    return _embedding_model


def get_embedding(text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> list[float]:
    """Generate embedding vector for a single text.

    Args:
        text: The text to embed.
        task_type: One of RETRIEVAL_DOCUMENT, RETRIEVAL_QUERY, etc.

    Returns:
        A list of floats (768-dimensional vector for text-embedding-004).
    """
    model = _get_embedding_model()
    inputs = [TextEmbeddingInput(text=text, task_type=task_type)]
    embeddings = model.get_embeddings(inputs)
    return embeddings[0].values


def get_embeddings_batch(
    texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT"
) -> list[list[float]]:
    """Generate embedding vectors for a batch of texts.

    Args:
        texts: List of texts to embed.
        task_type: The embedding task type.

    Returns:
        A list of embedding vectors.
    """
    model = _get_embedding_model()
    inputs = [TextEmbeddingInput(text=t, task_type=task_type) for t in texts]
    embeddings = model.get_embeddings(inputs)
    return [e.values for e in embeddings]


def store_document(content: str, metadata: dict) -> str:
    """Embed a document and store it in Firestore with vector.

    Args:
        content: The text content to store.
        metadata: Dict with keys like source_file, category, title, chunk_index.

    Returns:
        The Firestore document ID.
    """
    db = get_db()
    vector = get_embedding(content, task_type="RETRIEVAL_DOCUMENT")

    _, doc_ref = db.collection(settings.firestore_collection_knowledge).add(
        {
            "content": content,
            "metadata": metadata,
            "embedding": Vector(vector),
            "created_at": firestore_module.SERVER_TIMESTAMP,
        }
    )
    return doc_ref.id


# COSINE distance 門檻：0=完全相同、2=相反。超過此值視為「不相關」不回傳。
# 沒有門檻時 find_nearest 永遠回最近 top_k 筆，冷門問題會撈到不相干文件，
# 而 prompt 又強制引用知識庫 → 產生「檢索性幻覺」。
MAX_COSINE_DISTANCE = 0.45


def search_similar(
    query: str, top_k: int = 5, max_distance: float = MAX_COSINE_DISTANCE
) -> list[dict]:
    """Search for similar documents using Firestore Vector Search.

    Args:
        query: The search query text.
        top_k: Number of results to return.
        max_distance: COSINE distance 上限，超過視為不相關。

    Returns:
        List of dicts with content, metadata, and distance（越小越相關），
        已過濾掉超過 max_distance 的結果，可能為空 list。
    """
    db = get_db()
    query_vector = get_embedding(query, task_type="RETRIEVAL_QUERY")

    collection_ref = db.collection(settings.firestore_collection_knowledge)

    results = collection_ref.find_nearest(
        vector_field="embedding",
        query_vector=Vector(query_vector),
        distance_measure=DistanceMeasure.COSINE,
        limit=top_k,
        distance_result_field="vector_distance",
    ).get()

    out: list[dict] = []
    for doc in results:
        data = doc.to_dict() or {}
        distance = data.get("vector_distance")
        if distance is not None and distance > max_distance:
            continue
        out.append(
            {
                "content": data.get("content", ""),
                "metadata": data.get("metadata", {}),
                "distance": distance,
            }
        )
    return out


def get_collection_stats() -> dict:
    """Get statistics about the knowledge collection."""
    db = get_db()
    collection_ref = db.collection(settings.firestore_collection_knowledge)

    docs = collection_ref.select(["metadata"]).get()

    categories = set()
    last_updated = None
    count = 0

    for doc in docs:
        count += 1
        data = doc.to_dict() or {}
        meta = data.get("metadata", {})
        if cat := meta.get("category"):
            categories.add(cat)
        created = data.get("created_at")
        if created and (last_updated is None or created > last_updated):
            last_updated = created

    return {
        "total_documents": count,
        "categories": sorted(categories),
        "last_updated": str(last_updated) if last_updated else None,
    }
