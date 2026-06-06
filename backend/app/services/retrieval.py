import re
import logging
from app.services.embeddings import embed_query
from app.services.query_analysis import analyze_query
from app.store import qdrant_store
from app.config import settings

logger = logging.getLogger(__name__)


async def retrieve_chunks(session_id: str, question: str) -> list[dict]:
    """
    Multi-step retrieval:
    1. Analyze the question into focused sub-queries
    2. Retrieve top-K chunks for each sub-query
    3. Deduplicate by text content, re-rank by score
    """
    sub_queries = await analyze_query(question)

    seen: set[str] = set()
    all_chunks: list[dict] = []

    for sub_q in sub_queries:
        vector = await embed_query(sub_q)
        results = await qdrant_store.search(
            session_id=session_id,
            vector=vector,
            top_k=settings.top_k,
        )
        for r in results:
            # Deduplicate by the first 120 chars of text
            key = r["payload"].get("text", "")[:120]
            if key not in seen:
                seen.add(key)
                all_chunks.append(r)

    # Re-rank by score and cap at top_k * 2 so the prompt stays focused
    all_chunks.sort(key=lambda x: x["score"], reverse=True)
    final = all_chunks[: settings.top_k * 2]
    logger.info(
        "Multi-step retrieval: %d sub-queries → %d unique chunks for session %s",
        len(sub_queries), len(final), session_id,
    )
    return final


def build_prompt(question: str, chunks: list[dict], history: list[dict]) -> list[dict]:
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        p = chunk["payload"]
        section = p.get("section", "").strip()
        label = f"[{i}]"
        if section:
            label += f" {section} —"
        label += f" page {p['page']}"
        context_parts.append(f"{label}\n{p['text']}")
    context = "\n\n".join(context_parts)

    system = (
        "You are a helpful assistant that answers questions strictly about the provided PDF document.\n\n"
        "Rules:\n"
        "- Answer ONLY from the context below. Do not use outside knowledge.\n"
        "- When your answer draws directly from a source, place its number inline, e.g. [1] or [2].\n"
        "- Only cite a source if you actually used it. Do NOT cite sources that are not relevant to the answer.\n"
        "- If the context does not contain enough information to answer, say so clearly — do not guess and do not cite.\n"
        "- Be concise.\n\n"
        f"CONTEXT:\n{context}"
    )

    messages = [{"role": "system", "content": system}]
    for msg in history[-6:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": question})
    return messages


def filter_citations(response_text: str, chunks: list[dict]) -> list[dict]:
    """Return only the chunks whose [N] marker appears in the response."""
    used = {int(m) for m in re.findall(r"\[(\d+)\]", response_text)}
    result = []
    seen_pages: set[int] = set()
    for i, chunk in enumerate(chunks, 1):
        if i not in used:
            continue
        page = chunk["payload"].get("page", 1)
        if page in seen_pages:
            continue
        seen_pages.add(page)
        result.append({
            "doc_id": chunk["payload"]["doc_id"],
            "page": page,
            "section": chunk["payload"].get("section", ""),
        })
    return result
