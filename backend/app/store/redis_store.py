import json
import time
from typing import Optional
import redis.asyncio as aioredis
from app.config import settings

_redis: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def create_session(sid: str) -> None:
    r = await get_redis()
    now = int(time.time())
    expires_at = now + settings.idle_ttl_seconds
    pipe = r.pipeline()
    pipe.hset(f"session:{sid}", mapping={
        "created_at": now,
        "expires_at": expires_at,
        "status": "active",
        "doc_ids": json.dumps([]),
    })
    pipe.expire(f"session:{sid}", settings.idle_ttl_seconds)
    pipe.zadd("sessions:expiry", {sid: expires_at})
    await pipe.execute()


async def get_session(sid: str) -> Optional[dict]:
    r = await get_redis()
    data = await r.hgetall(f"session:{sid}")
    if not data:
        return None
    data["doc_ids"] = json.loads(data.get("doc_ids", "[]"))
    return data


async def refresh_session(sid: str) -> bool:
    r = await get_redis()
    exists = await r.exists(f"session:{sid}")
    if not exists:
        return False
    now = int(time.time())
    expires_at = now + settings.idle_ttl_seconds
    if settings.max_session_age_seconds > 0:
        session = await r.hgetall(f"session:{sid}")
        created_at = int(session.get("created_at", now))
        hard_cap = created_at + settings.max_session_age_seconds
        expires_at = min(expires_at, hard_cap)
    pipe = r.pipeline()
    pipe.hset(f"session:{sid}", "expires_at", expires_at)
    pipe.expire(f"session:{sid}", settings.idle_ttl_seconds)
    pipe.expire(f"conv:{sid}", settings.idle_ttl_seconds)
    pipe.expire(f"docs:{sid}", settings.idle_ttl_seconds)
    pipe.zadd("sessions:expiry", {sid: expires_at})
    await pipe.execute()
    return True


async def add_doc_to_session(sid: str, doc_id: str) -> None:
    r = await get_redis()
    session = await r.hgetall(f"session:{sid}")
    doc_ids = json.loads(session.get("doc_ids", "[]"))
    if doc_id not in doc_ids:
        doc_ids.append(doc_id)
    await r.hset(f"session:{sid}", "doc_ids", json.dumps(doc_ids))
    await r.sadd(f"docs:{sid}", doc_id)


async def set_doc_status(sid: str, doc_id: str, status: str) -> None:
    r = await get_redis()
    await r.hset(f"session:{sid}", f"doc_status:{doc_id}", status)


async def get_doc_status(sid: str, doc_id: str) -> Optional[str]:
    r = await get_redis()
    return await r.hget(f"session:{sid}", f"doc_status:{doc_id}")


async def append_message(sid: str, message: dict) -> None:
    r = await get_redis()
    await r.rpush(f"conv:{sid}", json.dumps(message))


async def get_messages(sid: str) -> list:
    r = await get_redis()
    raw = await r.lrange(f"conv:{sid}", 0, -1)
    return [json.loads(m) for m in raw]


async def delete_session(sid: str) -> None:
    r = await get_redis()
    pipe = r.pipeline()
    pipe.delete(f"session:{sid}", f"conv:{sid}", f"docs:{sid}")
    pipe.zrem("sessions:expiry", sid)
    await pipe.execute()


async def get_expired_sessions(now: Optional[int] = None) -> list[str]:
    r = await get_redis()
    if now is None:
        now = int(time.time())
    return await r.zrangebyscore("sessions:expiry", "-inf", now)
