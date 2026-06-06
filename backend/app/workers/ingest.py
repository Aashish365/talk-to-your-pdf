import logging
from app.services.extraction import extract_pdf
from app.services.chunking import chunk_elements
from app.services.embeddings import embed_texts
from app.store import qdrant_store, redis_store

logger = logging.getLogger(__name__)


async def ingest_document(sid: str, doc_id: str, ws_send=None) -> None:
    """Background ingestion: extract → chunk → embed → upsert."""
    async def notify(state: str, error: str = None):
        if ws_send:
            msg = {"type": "status", "doc_id": doc_id, "state": state}
            if error:
                msg["error"] = error
            try:
                await ws_send(msg)
            except Exception:
                pass

    try:
        await redis_store.set_doc_status(sid, doc_id, "processing")
        await notify("processing")

        # 1. Extract
        elements = await extract_pdf(sid, doc_id)
        if not elements:
            raise ValueError("No text extracted from PDF")

        # 2. Chunk
        chunks = chunk_elements(elements, doc_id, sid)

        # 3. Embed
        texts = [c["text"] for c in chunks]
        vectors = await embed_texts(texts)

        # 4. Ensure collection exists with correct vector size
        if vectors:
            await qdrant_store.ensure_collection(len(vectors[0]))

        # 5. Build points and upsert
        points = [
            {"id": c["id"], "vector": v, "payload": c["payload"]}
            for c, v in zip(chunks, vectors)
        ]
        await qdrant_store.upsert_chunks(points)

        await redis_store.set_doc_status(sid, doc_id, "ready")
        await notify("ready")
        logger.info("Ingestion complete: session=%s doc=%s chunks=%d", sid, doc_id, len(chunks))

    except Exception as e:
        logger.error("Ingestion failed: session=%s doc=%s error=%s", sid, doc_id, e)
        await redis_store.set_doc_status(sid, doc_id, "error")
        await notify("error", str(e))
