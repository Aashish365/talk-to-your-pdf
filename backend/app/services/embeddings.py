import httpx
from app.config import settings


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts via Ollama."""
    vectors = []
    async with httpx.AsyncClient(timeout=120) as client:
        for text in texts:
            resp = await client.post(
                f"{settings.ollama_url}/api/embeddings",
                json={"model": settings.ollama_embed_model, "prompt": text},
            )
            resp.raise_for_status()
            vectors.append(resp.json()["embedding"])
    return vectors


async def embed_query(text: str) -> list[float]:
    vectors = await embed_texts([text])
    return vectors[0]
