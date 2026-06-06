from qdrant_client import AsyncQdrantClient
from typing import Optional
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue,
    FilterSelector,
)
from app.config import settings
from typing import Optional

_client: Optional[AsyncQdrantClient] = None


async def get_client() -> AsyncQdrantClient:
    global _client
    if _client is None:
        _client = AsyncQdrantClient(url=settings.qdrant_url)
    return _client


async def ensure_collection(vector_size: int) -> None:
    client = await get_client()
    existing = [c.name for c in (await client.get_collections()).collections]
    if settings.qdrant_collection not in existing:
        await client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )


async def upsert_chunks(points: list[dict]) -> None:
    client = await get_client()
    qdrant_points = [
        PointStruct(
            id=p["id"],
            vector=p["vector"],
            payload=p["payload"],
        )
        for p in points
    ]
    await client.upsert(
        collection_name=settings.qdrant_collection,
        points=qdrant_points,
    )


async def search(
    session_id: str,
    vector: list[float],
    top_k: int,
    doc_id: Optional[str] = None,
) -> list[dict]:
    client = await get_client()
    must = [FieldCondition(key="session_id", match=MatchValue(value=session_id))]
    if doc_id:
        must.append(FieldCondition(key="doc_id", match=MatchValue(value=doc_id)))
    results = await client.search(
        collection_name=settings.qdrant_collection,
        query_vector=vector,
        query_filter=Filter(must=must),
        limit=top_k,
        with_payload=True,
    )
    return [{"score": r.score, "payload": r.payload} for r in results]


async def delete_by_session(session_id: str) -> None:
    client = await get_client()
    try:
        await client.delete(
            collection_name=settings.qdrant_collection,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[FieldCondition(key="session_id", match=MatchValue(value=session_id))]
                )
            ),
        )
    except Exception:
        pass
