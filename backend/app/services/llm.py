import httpx
import json
from typing import AsyncGenerator
from app.config import settings


async def stream_chat(messages: list[dict]) -> AsyncGenerator[str, None]:
    """Stream tokens from Ollama chat completion."""
    payload = {
        "model": settings.ollama_gen_model,
        "messages": messages,
        "stream": True,
    }
    async with httpx.AsyncClient(timeout=300) as client:
        async with client.stream(
            "POST",
            f"{settings.ollama_url}/api/chat",
            json=payload,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                token = data.get("message", {}).get("content", "")
                if token:
                    yield token
                if data.get("done"):
                    break
