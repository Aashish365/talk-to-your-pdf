import uuid
from app.store import redis_store, files


async def create_session() -> str:
    sid = str(uuid.uuid4())
    await redis_store.create_session(sid)
    files.create_session_dir(sid)
    return sid


async def end_session(sid: str) -> None:
    from app.lifecycle.sweeper import cleanup_session
    await cleanup_session(sid)


async def refresh(sid: str) -> bool:
    return await redis_store.refresh_session(sid)
