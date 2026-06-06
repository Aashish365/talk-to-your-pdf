from fastapi import APIRouter, HTTPException
from app.lifecycle import sessions as sess_lifecycle
from app.store import redis_store

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", status_code=201)
async def create_session():
    sid = await sess_lifecycle.create_session()
    return {"session_id": sid}


@router.delete("/{sid}", status_code=204)
async def end_session(sid: str):
    session = await redis_store.get_session(sid)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await sess_lifecycle.end_session(sid)
