import asyncio
import chromadb
from sentence_transformers import SentenceTransformer
from app.config import settings

# Module-level singletons (populated by init_search())
_embedding_model: SentenceTransformer | None = None
_chroma_client: chromadb.ClientAPI | None = None
_collection = None  # chromadb.Collection


def init_search() -> None:
    """
    Load embedding model and connect to ChromaDB.
    Called once at FastAPI startup via lifespan.
    """
    global _embedding_model, _chroma_client, _collection

    print("Loading embedding model...")
    _embedding_model = SentenceTransformer(settings.embedding_model)

    _chroma_client = chromadb.PersistentClient(path=settings.chroma_path)
    _collection = _chroma_client.get_or_create_collection("documents")

    print("Search initialized.")


async def query_narrative(
    message: str,
    building_id: str | None = None,
    top_k: int | None = None,
) -> list[str]:
    """
    Query ChromaDB for relevant narrative chunks.

    Args:
        message: The guest's message to embed and search
        building_id: Optional filter by building (also includes "general" docs)
        top_k: Number of results (defaults to settings.top_k_chunks)

    Returns:
        List of chunk text strings (may be empty if collection is empty)
    """
    if top_k is None:
        top_k = settings.top_k_chunks

    # Get collection count first
    count = await asyncio.to_thread(_collection.count)

    # Return empty list if collection is empty
    if count == 0:
        return []

    # Embed the message using asyncio.to_thread
    embedding = await asyncio.to_thread(
        lambda: _embedding_model.encode([message]).tolist()[0]
    )

    # Build ChromaDB where filter
    where_filter = None
    if building_id is not None:
        where_filter = {
            "$or": [
                {"building_id": {"$eq": building_id}},
                {"building_id": {"$eq": "general"}},
            ]
        }

    # Query ChromaDB
    n_results = min(top_k, count)
    results = await asyncio.to_thread(
        lambda: _collection.query(
            query_embeddings=[embedding],
            n_results=n_results,
            where=where_filter,
            include=["documents"],
        )
    )

    # Return documents list or empty list
    if results["documents"]:
        return results["documents"][0]
    return []
