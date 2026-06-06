import json
import re
import logging
from app.services.llm import call_chat

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a search query optimizer for a document retrieval system.\n\n"
    "Given a user question, output a JSON array of 1 to 3 focused search queries "
    "that together cover all the information needed to answer the question.\n\n"
    "Rules:\n"
    "- Simple or direct questions → 1 rewritten query (keyword-rich)\n"
    "- Complex or multi-part questions → up to 3 independent sub-queries\n"
    "- Each query must be concise and optimized for semantic vector search\n"
    "- Do NOT answer the question\n\n"
    "Return ONLY a JSON array of strings. No explanation. No markdown fences.\n\n"
    'Example input: "What are the main findings and how do they compare to prior work?"\n'
    'Example output: ["main findings key results", "comparison prior work related studies"]'
)


async def analyze_query(question: str) -> list[str]:
    """
    Decompose the user question into 1–3 focused sub-queries for retrieval.
    Falls back to the original question if analysis fails.
    """
    try:
        raw = await call_chat([
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": question},
        ])
        match = re.search(r'\[.*?\]', raw, re.DOTALL)
        if match:
            queries = json.loads(match.group())
            if (
                isinstance(queries, list)
                and len(queries) >= 1
                and all(isinstance(q, str) and q.strip() for q in queries)
            ):
                result = [q.strip() for q in queries[:3]]
                logger.info("Query analysis: %d sub-queries for %r", len(result), question[:60])
                return result
    except Exception as e:
        logger.warning("Query analysis failed, using original question: %s", e)

    return [question]
