import os
import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Header, Query
from fastapi.responses import FileResponse
from app.store import redis_store, files
from app.workers.ingest import ingest_document
from app.config import settings

router = APIRouter(prefix="/documents", tags=["documents"])

MAX_BYTES = settings.max_upload_mb * 1024 * 1024


@router.post("", status_code=202)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    x_session_id: str = Header(...),
):
    session = await redis_store.get_session(x_session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds {settings.max_upload_mb}MB limit")

    doc_id = str(uuid.uuid4())
    await files.save_upload(x_session_id, doc_id, data)
    await redis_store.add_doc_to_session(x_session_id, doc_id)
    await redis_store.set_doc_status(x_session_id, doc_id, "processing")

    background_tasks.add_task(ingest_document, x_session_id, doc_id)

    return {"doc_id": doc_id, "status": "processing"}


@router.get("/{doc_id}")
async def get_document_status(doc_id: str, x_session_id: str = Header(...)):
    session = await redis_store.get_session(x_session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    status = await redis_store.get_doc_status(x_session_id, doc_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Document not found")

    return {"doc_id": doc_id, "status": status}


@router.get("/{doc_id}/file")
async def serve_document(
    doc_id: str,
    session_id: str = Query(None),
    x_session_id: str = Header(None),
):
    # Accept session ID from either query param (browser URL) or header (API calls)
    sid = session_id or x_session_id
    if not sid:
        raise HTTPException(status_code=400, detail="session_id required")

    session = await redis_store.get_session(sid)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    path = files.pdf_path(sid, doc_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(path, media_type="application/pdf")
