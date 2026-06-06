import asyncio
import logging
from app.store import redis_store, qdrant_store, files
from app.config import settings

logger = logging.getLogger(__name__)


async def cleanup_session(sid: str) -> None:
    """Idempotent cleanup: remove vectors, files, and Redis keys for a session."""
    try:
        await qdrant_store.delete_by_session(sid)
    except Exception as e:
        logger.warning("Qdrant cleanup failed for %s: %s", sid, e)

    try:
        files.delete_session_dir(sid)
    except Exception as e:
        logger.warning("File cleanup failed for %s: %s", sid, e)

    try:
        await redis_store.delete_session(sid)
    except Exception as e:
        logger.warning("Redis cleanup failed for %s: %s", sid, e)


async def run_sweeper() -> None:
    """Periodically scan and clean up expired sessions."""
    logger.info("Session sweeper started (interval=%ds)", settings.sweeper_interval_seconds)
    while True:
        await asyncio.sleep(settings.sweeper_interval_seconds)
        try:
            expired = await redis_store.get_expired_sessions()
            for sid in expired:
                logger.info("Sweeper cleaning expired session %s", sid)
                await cleanup_session(sid)
        except Exception as e:
            logger.error("Sweeper error: %s", e)
